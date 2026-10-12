"""Health checks and local SQLite backup/restore.

Operational routes stay here so planner handlers do not own database snapshots.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

LOG = logging.getLogger("align")
ROOT = Path(__file__).resolve().parent
MAX_LOCAL_BACKUP_BYTES = 100 * 1024 * 1024


def health_status() -> dict:
    """Return operational metadata without exposing paths, credentials, or user data."""
    import app as align
    from sqlite_support import connect, postgres_enabled

    if postgres_enabled():
        from postgres_support import verify_hosted_storage
        available = False
        try:
            verify_hosted_storage()
            available = True
        except (RuntimeError, sqlite3.Error):
            LOG.error("Hosted database health check failed")
        return {
            "version": {"build": align.BUILD_VERSION, "app": align.APP_VERSION},
            "mode": "beta" if align.BETA_MODE else "normal",
            "database": {"available": available, "backend": "postgres",
                         "integrity": "not_checked"},
            "migrations": {"available": False, "applied": False, "managed": "externally"},
        }
    database_available = False
    database_integrity = "unavailable"
    migrations_available = all(
        (align.migration_runner.ROOT / filename).is_file()
        for filename in ("149_asset_studio.sql", "149_transport.sql", "150_calendar_links.sql", "151_sections.sql")
    )
    migrations_applied = False
    try:
        if align.current_database().is_file():
            with connect(align.current_database().as_uri() + "?mode=ro", uri=True) as connection:
                database_available = True
                database_integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
                table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
                ).fetchone()
                if table:
                    placeholders = ','.join('?' for _ in align.EXPECTED_MIGRATIONS)
                    applied = {
                        row[0] for row in connection.execute(
                            f"SELECT migration_id FROM schema_migrations WHERE migration_id IN ({placeholders})",
                            align.EXPECTED_MIGRATIONS,
                        )
                    }
                    migrations_applied = set(align.EXPECTED_MIGRATIONS) <= applied
    except (OSError, sqlite3.Error):
        LOG.exception("Health check could not inspect the Align database")
    return {
        "version": {"build": align.BUILD_VERSION, "app": align.APP_VERSION},
        "mode": "beta" if align.BETA_MODE else "normal",
        "database": {"available": database_available, "integrity": database_integrity},
        "migrations": {"available": migrations_available, "applied": migrations_applied},
    }


def local_database_backup(database: Path) -> bytes:
    """Return a consistent SQLite snapshot without exposing the database path."""
    database = Path(database)
    if not database.is_file():
        raise ValueError("The local Align database is not available.")
    with tempfile.TemporaryDirectory(prefix="align-backup-") as directory:
        snapshot = Path(directory) / "align.sqlite3"
        source = sqlite3.connect(database, timeout=30)
        target = sqlite3.connect(snapshot, timeout=30)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        if snapshot.stat().st_size > MAX_LOCAL_BACKUP_BYTES:
            raise ValueError("This database is too large for a browser backup (100 MB maximum).")
        return snapshot.read_bytes()


def local_backup_directory(database: Path) -> Path:
    configured = os.environ.get("ALIGN_LOCAL_BACKUP_DIR")
    if configured:
        return Path(configured)
    database = Path(database)
    master = ROOT.parent / "Master"
    if database.parent.resolve() == ROOT.resolve() and master.is_dir():
        return master / "Backups"
    return database.parent / "Backups"


def restore_local_database(database: Path, payload: bytes) -> None:
    """Validate a local backup, save the current database, then restore it."""
    import app as align

    if not payload or len(payload) > MAX_LOCAL_BACKUP_BYTES:
        raise ValueError("Choose a valid Align SQLite backup smaller than 100 MB.")
    if not payload.startswith(b"SQLite format 3\x00"):
        raise ValueError("This file is not an Align SQLite backup.")

    database = Path(database)
    if not database.is_file():
        raise ValueError("The local Align database is not available.")
    with tempfile.TemporaryDirectory(prefix="align-restore-") as directory:
        candidate = Path(directory) / "candidate.sqlite3"
        candidate.write_bytes(payload)
        source = sqlite3.connect(candidate.as_uri() + "?mode=ro", uri=True, timeout=30)
        try:
            if source.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("The backup failed its SQLite integrity check.")
            tables = {
                row[0] for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            has_legacy_planner = "shifts" in tables
            has_v3_core = {"personal_items", "organiser_sections"} <= tables
            if "schema_migrations" not in tables or "settings" not in tables or not (has_legacy_planner or has_v3_core):
                raise ValueError("This SQLite file does not contain a complete Align database.")

            safety_copy = local_database_backup(database)
            backup_dir = local_backup_directory(database)
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            safety_path = backup_dir / f"align-pre-restore-{timestamp}.sqlite3"
            with safety_path.open("xb") as backup_file:
                backup_file.write(safety_copy)

            target = sqlite3.connect(database, timeout=30)
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()

    align.initialise_database_at(database)


def handle(handler, app, method) -> bool:
    """Own /api/health and local backup routes. Return False for everything else."""
    path = urlparse(handler.path).path
    if method == "GET" and path == "/api/health":
        handler.send_json(200, health_status())
        return True
    if method == "GET" and path == "/api/local-backup":
        if not handler.require_local_backup_admin():
            return True
        try:
            body = local_database_backup(app.current_database())
        except ValueError as error:
            code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE if "too large" in str(error) else HTTPStatus.SERVICE_UNAVAILABLE
            handler.send_json(code, {"error": str(error)})
            return True
        except (OSError, sqlite3.Error):
            handler.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "The local database backup could not be created."})
            return True
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        handler.send_bytes(200, body, "application/vnd.sqlite3", f"align-backup-{timestamp}.sqlite3")
        return True
    if method == "POST" and path == "/api/local-backup/restore":
        if not handler.require_local_backup_admin():
            return True
        if handler.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/vnd.sqlite3":
            handler.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Choose an Align SQLite backup file."})
            return True
        try:
            length = int(handler.headers.get("Content-Length", "0"))
        except ValueError:
            handler.send_json(HTTPStatus.BAD_REQUEST, {"error": "The backup upload size is invalid."})
            return True
        if length <= 0 or length > MAX_LOCAL_BACKUP_BYTES:
            handler.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Choose a valid Align SQLite backup smaller than 100 MB."})
            return True
        payload = handler.rfile.read(length)
        if len(payload) != length:
            handler.send_json(HTTPStatus.BAD_REQUEST, {"error": "The backup upload was incomplete."})
            return True
        manager = app.ICLOUD_MANAGER
        if manager and (manager.enabled or manager.client):
            handler.send_json(HTTPStatus.CONFLICT, {"error": "Disconnect iCloud on this PC before restoring a backup, then reconnect after you review the restored data."})
            return True
        try:
            restore_local_database(app.current_database(), payload)
        except ValueError as error:
            handler.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return True
        except (OSError, sqlite3.Error) as error:
            app.LOG.error("Local database restore failed (%s)", type(error).__name__)
            handler.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The restore could not be completed. If it had started, an automatic pre-restore backup was saved locally."})
            return True
        handler.send_json(200, {"ok": True, "safety_copy_created": True})
        return True
    return False

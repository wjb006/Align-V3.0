"""Adopt an existing Align database without replacing newer saved data."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from desktop.errors import DesktopError
from desktop.paths import DATABASE_NAME

_ALIGN_TABLES = ("settings", "organiser_sections", "organiser_events", "schema_migrations", "builder_records")


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)


@contextmanager
def _readonly(path: Path):
    """Open a database and close it before the caller renames or deletes the file.

    sqlite3's own context manager commits, and it does not close the
    connection. On Windows an unclosed connection keeps the file locked, so
    adopting a database then fails with "the process cannot access the file".
    """
    connection = _connect_readonly(path)
    try:
        yield connection
    finally:
        connection.close()


def integrity_ok(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    try:
        with _readonly(path) as connection:
            row = connection.execute("PRAGMA quick_check").fetchone()
        return bool(row) and row[0] == "ok"
    except sqlite3.Error:
        return False


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def is_align_database(path: Path) -> bool:
    if not integrity_ok(path):
        return False
    try:
        with _readonly(path) as connection:
            return bool(_tables(connection) & set(_ALIGN_TABLES))
    except sqlite3.Error:
        return False


def content_score(path: Path) -> int:
    """Count meaningful saved Align content. -1 means unreadable."""
    if not path.is_file():
        return -1
    default_settings = {
        "user_name": "", "user_address": "", "user_phone": "",
        "user_home_location": "", "travel_bus": "true", "travel_rail": "true",
        "travel_walk": "true", "default_calendar": "Align",
        "notifications": "1", "onboarding_completed": "0",
    }
    try:
        with _readonly(path) as connection:
            names = _tables(connection)
            if not (names & set(_ALIGN_TABLES)):
                return 0

            score = 0
            for name in names:
                if name.startswith("sqlite_") or name in {
                    "schema_migrations", "alembic_version", "migration_history"
                }:
                    continue
                quoted = '"' + name.replace('"', '""') + '"'

                # Fresh V3 databases seed these rows for app startup. They
                # are infrastructure/defaults, not evidence of user content.
                if name == "settings":
                    for key, value in connection.execute(
                        "SELECT setting_key, setting_value FROM settings"
                    ):
                        value = str(value or "")
                        if key in default_settings and value == default_settings[key]:
                            continue
                        if value.strip():
                            score += 1
                    continue

                if name == "asset_categories":
                    columns = {row[1] for row in connection.execute(
                        'PRAGMA table_info("asset_categories")'
                    )}
                    if "built_in" in columns:
                        score += int(connection.execute(
                            "SELECT COUNT(*) FROM asset_categories WHERE built_in=0"
                        ).fetchone()[0])
                    else:
                        score += int(connection.execute(
                            f"SELECT COUNT(*) FROM {quoted}"
                        ).fetchone()[0])
                    continue

                if name == "transport_preferences":
                    columns = {row[1] for row in connection.execute(
                        'PRAGMA table_info("transport_preferences")'
                    )}
                    selected = [key for key in (
                        "arrival_buffer", "modes", "home_lat", "home_lon"
                    ) if key in columns]
                    if selected:
                        row = connection.execute(
                            "SELECT " + ", ".join('"' + key + '"' for key in selected)
                            + " FROM transport_preferences WHERE id=1"
                        ).fetchone()
                        defaults = {
                            "arrival_buffer": 10, "modes": '["bus","rail","walk"]',
                            "home_lat": None, "home_lon": None,
                        }
                        if row and any(value != defaults[key] for key, value in zip(selected, row)):
                            score += 1
                    continue

                if name == "icloud_config":
                    columns = [row[1] for row in connection.execute(
                        'PRAGMA table_info("icloud_config")'
                    )]
                    row = connection.execute(
                        "SELECT * FROM icloud_config WHERE id=1"
                    ).fetchone()
                    if row and any(
                        value not in (None, "", "[]")
                        for key, value in zip(columns, row)
                        if key not in {"id", "instance_id"}
                    ):
                        score += 1
                    continue

                if name == "calendar_sync_state":
                    columns = {row[1] for row in connection.execute(
                        'PRAGMA table_info("calendar_sync_state")'
                    )}
                    if "revision" in columns:
                        row = connection.execute(
                            "SELECT revision FROM calendar_sync_state WHERE id=1"
                        ).fetchone()
                        if row and int(row[0] or 0) > 0:
                            score += 1
                    continue

                if name == "builder_config":
                    columns = {row[1] for row in connection.execute(
                        'PRAGMA table_info("builder_config")'
                    )}
                    if {"revision", "published_revision"} <= columns:
                        row = connection.execute(
                            "SELECT revision,published_revision FROM builder_config WHERE id=1"
                        ).fetchone()
                        if row and max(int(row[0] or 0), int(row[1] or 0)) > 1:
                            score += 1
                    continue

                score += int(connection.execute(
                    f"SELECT COUNT(*) FROM {quoted}"
                ).fetchone()[0])
            return score
    except sqlite3.Error:
        return -1

def inspect_database(data_dir: Path, legacy_paths: list[Path]) -> dict:
    """Describe the safe database choice. This does not write anything."""
    data_dir = Path(data_dir)
    target = data_dir / DATABASE_NAME
    try:
        target_key = target.resolve()
    except OSError:
        target_key = target
    legacy = []
    for path in legacy_paths:
        path = Path(path)
        try:
            if path.resolve() == target_key:
                continue
        except OSError:
            continue
        if is_align_database(path):
            legacy.append(path)
    legacy.sort(key=lambda item: (content_score(item), item.stat().st_mtime), reverse=True)
    best = legacy[0] if legacy else None
    target_score = content_score(target) if target.is_file() else -1
    best_score = content_score(best) if best is not None else -1

    if target.is_file() and not integrity_ok(target):
        action = "replace-unreadable"
    elif target.is_file() and target_score > 0:
        action = "keep"
    elif best is not None and best_score > target_score:
        action = "copy"
    elif target.is_file() and is_align_database(target):
        action = "keep"
    elif best is not None:
        action = "copy"
    else:
        action = "create"
    return {
        "action": action,
        "database": target,
        "source": best,
        "target_score": target_score,
        "source_score": best_score,
    }


def _quarantine(path: Path, reason: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = path.with_name(f"{path.name}.{reason}-{stamp}")
    path.rename(destination)
    return destination


def copy_database(source: Path, target: Path) -> None:
    """Copy with SQLite's backup API, then swap the file into place."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    if partial.exists():
        partial.unlink()
    incoming = sqlite3.connect(source, timeout=30)
    outgoing = sqlite3.connect(partial, timeout=30)
    try:
        incoming.backup(outgoing)
    except sqlite3.Error as error:
        raise DesktopError("Align could not copy the existing planner database.") from error
    finally:
        outgoing.close()
        incoming.close()
    if not integrity_ok(partial):
        partial.unlink(missing_ok=True)
        raise DesktopError("The copied planner database failed its integrity check.")
    partial.replace(target)


def adopt_database(data_dir: Path, legacy_paths: list[Path]) -> dict:
    """Make the user-data database the one Align will open.

    An existing database that already has planner content is kept. A blank
    database is replaced only when an older install has the real records.
    Legacy files are never deleted.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    plan = inspect_database(data_dir, legacy_paths)
    target = Path(plan["database"])
    source = plan["source"]
    if plan["action"] == "keep":
        return {"action": "kept", "database": target, "source": None}
    if plan["action"] == "create":
        return {"action": "create-on-start", "database": target, "source": None}
    if source is None:
        raise DesktopError("Align found planner data it could not read, and there is no earlier copy to use.")
    if target.exists():
        reason = "unreadable" if plan["action"] == "replace-unreadable" else "blank"
        _quarantine(target, reason)
    copy_database(Path(source), target)
    if not is_align_database(target):
        raise DesktopError("Align could not prepare the saved planner database.")
    return {"action": "copied", "database": target, "source": Path(source)}

"""Adopt an existing Align database without replacing newer saved data."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from desktop.errors import DesktopError
from desktop.paths import DATABASE_NAME

_ALIGN_TABLES = ("settings", "organiser_sections", "organiser_events", "schema_migrations", "builder_records")


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)


def integrity_ok(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    try:
        with _connect_readonly(path) as connection:
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
        with _connect_readonly(path) as connection:
            return bool(_tables(connection) & set(_ALIGN_TABLES))
    except sqlite3.Error:
        return False


def content_score(path: Path) -> int:
    """How much planner content a database already holds. -1 means unreadable."""
    if not path.is_file():
        return -1
    try:
        with _connect_readonly(path) as connection:
            names = _tables(connection)
            if not (names & set(_ALIGN_TABLES)):
                return 0
            score = 0
            if "organiser_events" in names:
                score += int(connection.execute("SELECT COUNT(*) FROM organiser_events").fetchone()[0])
            if "organiser_sections" in names:
                score += int(connection.execute("SELECT COUNT(*) FROM organiser_sections").fetchone()[0])
            if "builder_records" in names:
                score += int(connection.execute("SELECT COUNT(*) FROM builder_records").fetchone()[0])
            if "settings" in names:
                named = connection.execute(
                    "SELECT setting_value FROM settings WHERE setting_key='user_name'"
                ).fetchone()
                if named and str(named[0]).strip():
                    score += 1
                onboarded = connection.execute(
                    "SELECT setting_value FROM settings WHERE setting_key='onboarding_completed'"
                ).fetchone()
                if onboarded and str(onboarded[0]) == "1":
                    score += 1
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

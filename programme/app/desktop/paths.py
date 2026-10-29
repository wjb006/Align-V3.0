"""Programme files stay separate from the planner database and logs."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from align_paths import source_root

DATABASE_NAME = "align.sqlite3"
LOG_NAME = "studio.log"
ERROR_LOG_NAME = "studio-error.log"


def install_dir() -> Path:
    """Folder that contains the programme the person launched."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return source_root()


def user_data_dir() -> Path:
    """Per-user folder for the database, logs, and desktop state.

    ALIGN_DATA_DIR wins when it is set. On Windows the default is
    %LOCALAPPDATA%\\Align. Elsewhere it is the XDG data home.
    """
    override = os.environ.get("ALIGN_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Align"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "align"


def database_path(data_dir: Path | None = None) -> Path:
    return Path(data_dir or user_data_dir()) / DATABASE_NAME


def legacy_database_candidates(programme_dir: Path | None = None) -> list[Path]:
    """Older installs kept align.sqlite3 beside the programme or under app/.

    ALIGN_LEGACY_DATABASES replaces this list. An empty value disables adoption.
    Separate several paths with the operating system's path separator.
    """
    override = os.environ.get("ALIGN_LEGACY_DATABASES")
    if override is not None:
        return [Path(part) for part in override.split(os.pathsep) if part.strip()]
    root = Path(programme_dir) if programme_dir is not None else install_dir()
    candidates = [root / DATABASE_NAME, root / "app" / DATABASE_NAME]
    checkout = source_root() / DATABASE_NAME
    if checkout not in candidates:
        candidates.append(checkout)
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique

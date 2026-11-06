"""Locate Align's source files in a checkout and in a PyInstaller bundle.

User data does not live here. The desktop programme keeps databases and logs
in the per-user Align folder, outside the programme files.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def source_root() -> Path:
    """Directory that contains app.py, static/, and migrations/.

    ALIGN_APP_CODE is set only after the desktop programme has validated an
    update. A folder that does not contain the programme files is ignored.
    """
    chosen = os.environ.get("ALIGN_APP_CODE", "").strip()
    if chosen:
        try:
            resolved = Path(chosen).resolve()
        except OSError:
            resolved = Path(chosen)
        app_file = resolved / "app.py"
        pages = resolved / "static"
        if (
            app_file.is_file()
            and not app_file.is_symlink()
            and pages.is_dir()
            and not pages.is_symlink()
        ):
            return resolved
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_file(*parts: str) -> Path:
    """A file shipped beside the Align source, including inside a frozen bundle."""
    return source_root().joinpath(*parts)

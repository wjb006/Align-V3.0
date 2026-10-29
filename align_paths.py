"""Locate Align's source files in a checkout and in a PyInstaller bundle.

User data does not live here. The desktop programme keeps databases and logs
in the per-user Align folder, outside the programme files.
"""
from __future__ import annotations

import sys
from pathlib import Path


def source_root() -> Path:
    """Directory that contains app.py, static/, and migrations/."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_file(*parts: str) -> Path:
    """A file shipped beside the Align source, including inside a frozen bundle."""
    return source_root().joinpath(*parts)

"""Small Windows updater for the currently installed Align V3 Git branch."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys

from studio_update import update_from_github


def notify(title: str, message: str, error: bool = False) -> None:
    if os.name == "nt":
        style = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(None, message, title, style)
    else:
        print(f"{title}: {message}")


def main() -> int:
    try:
        result = update_from_github(lambda: None)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        notify("Align V3 update failed", str(exc), error=True)
        return 1
    notify("Align V3 updater", result["summary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

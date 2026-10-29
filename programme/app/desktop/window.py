"""Open Planner and Management Studio in a desktop window."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def windows_browser_candidates() -> list[str]:
    roots = [
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("ProgramFiles", ""),
        os.environ.get("LocalAppData", ""),
    ]
    paths: list[str] = []
    for root in roots:
        if not root:
            continue
        base = Path(root)
        paths.append(str(base / "Microsoft" / "Edge" / "Application" / "msedge.exe"))
        paths.append(str(base / "Google" / "Chrome" / "Application" / "chrome.exe"))
    return paths


def windows_app_command(url: str, exists=os.path.exists, candidates: list[str] | None = None) -> tuple[str, list[str]]:
    for candidate in windows_browser_candidates() if candidates is None else candidates:
        if exists(candidate):
            return candidate, [f"--app={url}", "--window-size=1360,900", "--new-window"]
    return "rundll32", ["url.dll,FileProtocolHandler", url]


def open_window(url: str) -> None:
    if os.name == "nt":
        command, args = windows_app_command(url)
        subprocess.Popen([command, *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        return
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603

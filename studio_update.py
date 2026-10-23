"""Download the latest Align main branch into this local folder."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        creationflags=flags,
    )


def current_commit() -> str:
    result = _git("rev-parse", "HEAD")
    if result.returncode != 0:
        raise RuntimeError("This Align folder is not a git checkout.")
    return result.stdout.strip()


def current_branch() -> str:
    result = _git("branch", "--show-current")
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch:
        raise RuntimeError("This Align folder is not on a named Git branch.")
    return branch


def update_from_github(initialise) -> dict:
    """Fast-forward this folder to its matching origin branch."""
    before = current_commit()
    branch = current_branch()
    result = _git("pull", "--ff-only", "origin", branch)
    message = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(message or "Update failed.")
    after = current_commit()
    changed = before != after
    if changed:
        initialise()
        message = f"{message} Restart Management Studio to load program changes.".strip()
    return {"ok": True, "changed": changed, "summary": message or "Already up to date."}

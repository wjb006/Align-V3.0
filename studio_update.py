"""Fast-forward this local folder to its configured GitHub branch."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _exe_root = Path(sys.executable).resolve().parent
    _nested_app = _exe_root / "V3.0"
    ROOT = _nested_app if (_nested_app / ".git").is_dir() else _exe_root
else:
    ROOT = Path(__file__).resolve().parent


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


def upstream_branch() -> tuple[str, str]:
    result = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if result.returncode != 0:
        raise RuntimeError("This Align checkout has no configured GitHub update branch.")
    upstream = result.stdout.strip()
    if "/" not in upstream:
        raise RuntimeError("The configured GitHub update branch could not be identified.")
    return tuple(upstream.split("/", 1))


def update_from_github(initialise) -> dict:
    """Fast-forward this folder to the upstream branch it is checked out from."""
    if getattr(sys, "frozen", False):
        raise RuntimeError(
            "This installed Align programme is updated by installing a new Windows package. "
            "Your saved planner data is kept."
        )
    before = current_commit()
    remote, branch = upstream_branch()
    result = _git("pull", "--ff-only", remote, branch)
    message = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(message or "Update failed.")
    after = current_commit()
    changed = before != after
    if changed:
        initialise()
        message = f"{message} Restart Management Studio to load program changes.".strip()
    return {"ok": True, "changed": changed, "summary": message or "Already up to date."}

"""Choose the Align code a desktop launch will run.

A validated download lives in the per-user folder ``app-code``. The Python
runtime stays in the programme. When the override is missing, incomplete, or
did not become healthy last time, launch uses the code bundled with the
programme.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "align-update.json"
INCOMING_NAME = "app-code.incoming"
CURRENT_NAME = "app-code"
PREVIOUS_NAME = "app-code.previous"
ATTEMPT_NAME = "app-code.attempt"
SCHEMA = 1
REPO = "wjb006/Align-V3.0"
BRANCH = "codex/align-v3-rebuild"
REQUIRED_FILES = (
    "app.py",
    "align_paths.py",
    "static/desktop.html",
    "static/index.html",
    "desktop/auth.py",
    "static/desktop-login.html",
    "static/desktop-login.css",
    "static/desktop-login.js",
)
PROGRAMME_ROOT_ENV = "ALIGN_PROGRAMME_ROOT"
APP_CODE_ENV = "ALIGN_APP_CODE"


def capture_programme_root() -> Path:
    """Remember the programme that was launched, before any override is chosen."""
    existing = os.environ.get(PROGRAMME_ROOT_ENV, "").strip()
    if existing:
        return Path(existing)
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parents[1]
    os.environ[PROGRAMME_ROOT_ENV] = str(root)
    return root


def programme_root() -> Path:
    return capture_programme_root()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _file_inside(root: Path, relative: str) -> bool:
    path = root.joinpath(*relative.split("/"))
    if path.is_symlink() or not path.is_file():
        return False
    if not _inside(path, root):
        return False
    try:
        return path.stat().st_size > 0
    except OSError:
        return False


def tree_problems(root: Path) -> str:
    """Return a short reason the folder cannot be loaded, or an empty string."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        return "The update folder is missing."
    static_dir = root / "static"
    migrations = root / "migrations"
    if static_dir.is_symlink() or not static_dir.is_dir():
        return "The update does not contain the Align pages."
    if migrations.is_symlink() or not migrations.is_dir():
        return "The update does not contain the Align database migrations."
    if not any(path.suffix == ".sql" and path.is_file() and not path.is_symlink() for path in migrations.iterdir()):
        return "The update does not contain the Align database migrations."
    for relative in REQUIRED_FILES:
        if not _file_inside(root, relative):
            return "The update is missing part of the Align programme."
    for relative in ("app.py", "align_paths.py"):
        path = root.joinpath(*relative.split("/"))
        try:
            compile(path.read_text(encoding="utf-8"), relative, "exec")
        except (OSError, SyntaxError, UnicodeError):
            return "The update could not be read as Align code."
    return ""


def read_manifest(root: Path) -> dict | None:
    path = Path(root) / MANIFEST_NAME
    if path.is_symlink() or not path.is_file() or not _inside(path, Path(root)):
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def manifest_problems(payload: dict | None) -> str:
    if not isinstance(payload, dict):
        return "The update is not marked as an Align download."
    if payload.get("schema") != SCHEMA:
        return "This programme does not understand that update."
    commit = payload.get("commit")
    if not isinstance(commit, str) or len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        return "The update does not name the commit it came from."
    if payload.get("repo") != REPO or payload.get("branch") != BRANCH:
        return "The update is not from the Align desktop branch."
    if not isinstance(payload.get("awaiting_health", False), bool):
        return "The update record is not valid."
    return ""


def write_manifest(root: Path, commit: str, *, awaiting_health: bool) -> None:
    payload = {
        "schema": SCHEMA,
        "repo": REPO,
        "branch": BRANCH,
        "commit": commit,
        "awaiting_health": awaiting_health,
    }
    path = Path(root) / MANIFEST_NAME
    temporary = path.with_suffix(".json.partial")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _quarantine(data_dir: Path, root: Path) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = data_dir / f"app-code.rejected-{stamp}"
    counter = 0
    while destination.exists():
        counter += 1
        destination = data_dir / f"app-code.rejected-{stamp}-{counter}"
    root.replace(destination)


def promote_incoming(data_dir: Path) -> bool:
    """Move a validated download into place. The previous folder is kept aside.

    Returns True when a download became the current override. A failure puts
    the previous override back and leaves the programme on its current code.
    """
    data_dir = Path(data_dir)
    incoming = data_dir / INCOMING_NAME
    if not incoming.exists():
        return False
    if tree_problems(incoming) or manifest_problems(read_manifest(incoming)):
        shutil.rmtree(incoming, ignore_errors=True)
        return False
    current = data_dir / CURRENT_NAME
    previous = data_dir / PREVIOUS_NAME
    if previous.exists():
        shutil.rmtree(previous)
    moved = False
    try:
        if current.exists():
            current.replace(previous)
            moved = True
        incoming.replace(current)
    except OSError:
        if moved and previous.exists() and not current.exists():
            previous.replace(current)
        shutil.rmtree(incoming, ignore_errors=True)
        return False
    return True


def consider_override(data_dir: Path, *, commit: bool = False) -> Path | None:
    """Return the override to load, or None to use the bundled programme.

    Only the server process commits to a download. That writes a marker before
    the new code is imported. If that process never becomes healthy, the next
    server start moves the download aside and uses the bundled programme. The
    previous download is kept on disk and is not loaded automatically.
    """
    data_dir = Path(data_dir)
    if commit:
        try:
            promote_incoming(data_dir)
        except OSError:
            return None
    root = data_dir / CURRENT_NAME
    if tree_problems(root):
        return None
    payload = read_manifest(root)
    problem = manifest_problems(payload)
    if problem:
        return None
    attempt = data_dir / ATTEMPT_NAME
    if payload.get("awaiting_health"):
        if not commit:
            return None
        if attempt.exists():
            try:
                _quarantine(data_dir, root)
            except OSError:
                return None
            attempt.unlink(missing_ok=True)
            return None
        try:
            attempt.write_text(str(payload.get("commit") or ""), encoding="utf-8")
        except OSError:
            return None
        return root.resolve()
    attempt.unlink(missing_ok=True)
    return root.resolve()


def mark_override_healthy(data_dir: Path) -> None:
    """Record that the override answered a local health check."""
    root = Path(data_dir) / CURRENT_NAME
    payload = read_manifest(root)
    if manifest_problems(payload):
        return
    if payload.get("awaiting_health"):
        write_manifest(root, str(payload["commit"]), awaiting_health=False)
    attempt = Path(data_dir) / ATTEMPT_NAME
    attempt.unlink(missing_ok=True)


def _use_tree(root: Path) -> None:
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    import desktop

    package = root / "desktop"
    if package.is_dir() and not package.is_symlink():
        package_text = str(package)
        if package_text not in desktop.__path__:
            desktop.__path__.insert(0, package_text)
    for name in list(sys.modules):
        if name.startswith("desktop.") and name not in {"desktop.__main__", "desktop.app_code"}:
            del sys.modules[name]


def prepare_runtime(*, commit: bool = False) -> Path | None:
    """Select the override before Align is imported.

    ``commit`` is for the server process. It installs a staged download and
    records the attempt. The launcher and a dry run use the proven override
    when there is one, and otherwise stay on the bundled code.
    """
    capture_programme_root()
    if commit:
        os.environ.pop(APP_CODE_ENV, None)
    else:
        chosen = os.environ.get(APP_CODE_ENV, "").strip()
        if chosen:
            path = Path(chosen)
            if not tree_problems(path) and not manifest_problems(read_manifest(path)):
                _use_tree(path)
                return path.resolve()
            os.environ.pop(APP_CODE_ENV, None)
    from desktop.paths import user_data_dir

    try:
        root = consider_override(user_data_dir(), commit=commit)
    except OSError:
        root = None
    if root is None:
        return None
    os.environ[APP_CODE_ENV] = str(root)
    _use_tree(root)
    return root


def watch_override_health(data_dir: Path) -> None:
    """After the server answers, keep the override. A crash leaves it unproven."""
    if not os.environ.get(APP_CODE_ENV):
        return
    import threading
    import time

    def confirm() -> None:
        from desktop.supervisor import fetch_health

        raw = os.environ.get("ALIGN_PORT", "8001").strip() or "8001"
        try:
            port = int(raw)
        except ValueError:
            return
        for _ in range(60):
            ready, _responding = fetch_health(port, timeout=1)
            if ready:
                try:
                    mark_override_healthy(data_dir)
                except OSError:
                    return
                return
            time.sleep(0.5)

    threading.Thread(target=confirm, name="AlignUpdateHealth", daemon=True).start()

"""Start the local Align server, or reuse one that is already this Align."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from align_paths import source_root
from desktop.errors import DesktopError
from desktop.paths import ERROR_LOG_NAME, LOG_NAME

ALIGN_APP_VERSION = "3.0"


def is_align_health(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    version = payload.get("version")
    if not isinstance(version, dict):
        return False
    try:
        build = int(version.get("build") or 0)
    except (TypeError, ValueError):
        return False
    return build > 0 and version.get("app") == ALIGN_APP_VERSION


def fetch_health(port: int, timeout: float = 2.0) -> tuple[bool, bool]:
    """Return (is_align, got_an_http_response)."""
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/health")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(65536)
    except urllib.error.HTTPError as error:
        error.close()
        return False, True
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False, False
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return False, True
    return is_align_health(payload), True


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def chosen_port(explicit: int | None = None) -> int:
    if explicit is not None:
        port = explicit
    else:
        raw = os.environ.get("ALIGN_PORT", "").strip()
        port = int(raw) if raw else 8001
    if port != 0 and not 1 <= port <= 65535:
        raise DesktopError(f"Port {port} is not a valid port number. Choose a port from 1 to 65535.")
    if port == 0:
        return free_port()
    return port


class ServerHandle:
    def __init__(self, process: subprocess.Popen[bytes] | None, port: int, started: bool) -> None:
        self.process = process
        self.port = port
        self.started = started

    def stop(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _server_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--serve"]
    return [sys.executable, "-m", "desktop", "--serve"]


def _tail(path: Path, limit: int = 20) -> str:
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-limit:]).strip()


def start_server(data_dir: Path, port: int, wait_seconds: float = 30.0) -> ServerHandle:
    """Start Align on loopback, or return the Align server already on this port."""
    ready, responding = fetch_health(port)
    if ready:
        return ServerHandle(None, port, started=False)
    if responding:
        raise DesktopError(
            f"Port {port} is already in use by something that is not Align. "
            "Close that programme or set ALIGN_PORT to another port."
        )

    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / LOG_NAME
    error_path = data_dir / ERROR_LOG_NAME
    log_file = log_path.open("ab")
    error_file = error_path.open("ab")
    env = os.environ.copy()
    env["ALIGN_DATA_DIR"] = str(data_dir)
    env["ALIGN_PORT"] = str(port)
    env["ALIGN_STUDIO_LOCAL"] = "1"
    env["ALIGN_BETA_MODE"] = "0"
    env["PYTHONUNBUFFERED"] = "1"
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(
            _server_command(),
            cwd=str(source_root() if not getattr(sys, "frozen", False) else data_dir),
            env=env,
            stdout=log_file,
            stderr=error_file,
            **kwargs,
        )
    except OSError as error:
        log_file.close()
        error_file.close()
        raise DesktopError("Align could not start the local server. Check that the programme files are intact.") from error
    finally:
        log_file.close()
        error_file.close()

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            detail = _tail(error_path) or _tail(log_path)
            extra = f"\n\n{detail}" if detail else ""
            raise DesktopError(
                f"Align stopped while it was opening. The log is in the Align data folder.{extra}"
            )
        ready, responding = fetch_health(port, timeout=1.0)
        if ready:
            return ServerHandle(process, port, started=True)
        if responding:
            process.terminate()
            raise DesktopError(
                f"Port {port} answered, but it is not Align. Close the other programme or set ALIGN_PORT."
            )
        time.sleep(0.3)
    if process.poll() is None:
        process.terminate()
    detail = _tail(error_path) or _tail(log_path)
    extra = f"\n\n{detail}" if detail else ""
    raise DesktopError(f"Align did not become ready on port {port}.{extra}")

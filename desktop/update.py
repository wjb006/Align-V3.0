"""Download Align code from GitHub and stage it for the next launch.

This is the installed programme's updater. It does not use git. A source
checkout still fast-forwards with git through studio_update. The download is
the commit just read from codex/align-v3-rebuild, over HTTPS, from GitHub only.
Checking on launch compares that commit and does not download it.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from desktop.app_code import (
    BRANCH,
    INCOMING_NAME,
    REPO,
    manifest_problems,
    read_manifest,
    tree_problems,
    write_manifest,
)
from desktop.build_info import COMMIT as STAMPED_COMMIT
from desktop.errors import DesktopError
from desktop.secrets import SecretStore, default_store

API_HOSTS = {"api.github.com", "codeload.github.com"}
COMMIT_URL = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
MAX_ZIP_BYTES = 100 * 1024 * 1024
MAX_MEMBER_BYTES = 20 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 150 * 1024 * 1024
PREFERENCES_NAME = "desktop-update.json"
STATUS_NAME = "desktop-update-status.json"
_APPLY_LOCK = threading.Lock()
_SHA = set("0123456789abcdef")


def _sha(value: object) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(char not in _SHA for char in value):
        return ""
    return value


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_preferences(data_dir: Path) -> dict:
    path = Path(data_dir) / PREFERENCES_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {"check_on_launch": payload.get("check_on_launch") is True}


def load_status(data_dir: Path) -> dict:
    path = Path(data_dir) / STATUS_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        return {}
    payload.pop("token", None)
    return payload


def _write_status(data_dir: Path, **fields: object) -> None:
    current = load_status(data_dir)
    current.update(fields)
    current.pop("token", None)
    _atomic_json(Path(data_dir) / STATUS_NAME, current)


def token_acceptable(value: str) -> bool:
    if not 8 <= len(value) <= 255:
        return False
    return all(char.isalnum() or char in "_-" for char in value)


def save_preferences(
    data_dir: Path,
    *,
    check_on_launch: bool | None = None,
    token: str | None = None,
    store: SecretStore | None = None,
) -> dict:
    """Save the launch choice and, when supplied, the token.

    ``token`` None leaves the saved token alone. An empty token removes it.
    The token is not written into the preferences file.
    """
    data_dir = Path(data_dir)
    preferences = load_preferences(data_dir)
    if check_on_launch is not None:
        preferences["check_on_launch"] = bool(check_on_launch)
    _atomic_json(data_dir / PREFERENCES_NAME, preferences)
    keeper = store if store is not None else default_store(data_dir)
    if token is not None:
        if token == "":
            keeper.clear()
        else:
            if not token_acceptable(token):
                raise DesktopError("That GitHub token cannot be saved.")
            keeper.save(token)
    return {"check_on_launch": preferences["check_on_launch"], "token_saved": bool(keeper.load())}


def read_git_head() -> str:
    """Identify a source checkout. This does not fetch or merge."""
    if getattr(sys, "frozen", False):
        return ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return _sha((result.stdout or "").strip())


def installed_commit(data_dir: Path | None = None) -> str:
    """Commit of the code this process would run, when that is known."""
    chosen = os.environ.get("ALIGN_APP_CODE", "").strip()
    if chosen:
        payload = read_manifest(Path(chosen))
        commit = _sha((payload or {}).get("commit"))
        if commit and not manifest_problems(payload):
            return commit
    if data_dir is not None:
        root = Path(data_dir) / "app-code"
        payload = read_manifest(root)
        if not tree_problems(root) and not manifest_problems(payload):
            commit = _sha((payload or {}).get("commit"))
            if commit and not (payload or {}).get("awaiting_health"):
                return commit
    stamped = _sha(STAMPED_COMMIT.strip())
    if stamped:
        return stamped
    return read_git_head()


def assert_github_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in API_HOSTS:
        raise DesktopError("Align only downloads updates over HTTPS from GitHub.")
    if parsed.username or parsed.password:
        raise DesktopError("Align only downloads updates over HTTPS from GitHub.")


class _GithubRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_github_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _scrub(text: str, token: str) -> str:
    if token and token in text:
        return text.replace(token, "saved-token")
    return text


def _public_http_error(status: int, token: str) -> DesktopError:
    if status in {401, 403} and token:
        return DesktopError("GitHub did not accept the saved token.")
    if status == 404:
        return DesktopError(
            "GitHub did not show that branch. If the repository is private, save a GitHub token in Settings."
        )
    if status == 403:
        return DesktopError("GitHub asked Align to wait before checking again.")
    return DesktopError("GitHub could not be checked.")


def _request(url: str, token: str, timeout: float):
    assert_github_https(url)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Align-Desktop",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    opener = build_opener(_GithubRedirect)
    return opener.open(request, timeout=timeout)


def _read_limited(response, limit: int) -> bytes:
    chunks = []
    total = 0
    while True:
        block = response.read(64 * 1024)
        if not block:
            break
        total += len(block)
        if total > limit:
            raise DesktopError("The update download was larger than Align will accept.")
        chunks.append(block)
    return b"".join(chunks)


class GithubTransport:
    def commit(self, token: str) -> str:
        try:
            with _request(COMMIT_URL, token, 20) as response:
                payload = json.loads(_read_limited(response, 1_000_000).decode("utf-8"))
        except HTTPError as error:
            error.close()
            raise _public_http_error(error.code, token) from None
        except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as error:
            raise DesktopError(_scrub("GitHub could not be checked.", token) if token else "GitHub could not be checked.") from error
        commit = _sha(payload.get("sha") if isinstance(payload, dict) else "")
        if not commit:
            raise DesktopError("GitHub did not name the latest Align commit.")
        return commit

    def zipball(self, sha: str, token: str) -> bytes:
        url = f"https://api.github.com/repos/{REPO}/zipball/{sha}"
        try:
            with _request(url, token, 120) as response:
                return _read_limited(response, MAX_ZIP_BYTES)
        except HTTPError as error:
            error.close()
            raise _public_http_error(error.code, token) from None
        except (URLError, TimeoutError, OSError) as error:
            message = _scrub(str(error), token)
            if message and "HTTPS" in message:
                raise DesktopError(message) from None
            raise DesktopError("The update could not be downloaded.") from None


def _skipped(relative: str) -> bool:
    parts = [part for part in relative.split("/") if part]
    if not parts:
        return True
    if ".git" in parts or "__pycache__" in parts:
        return True
    name = parts[-1]
    if name == ".env" or name.startswith(".env."):
        return True
    return name.endswith((".sqlite", ".sqlite3", ".db"))


def _member_is_link(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def extract_zip(payload: bytes, destination: Path, commit: str) -> None:
    """Unpack one GitHub project folder. Reject links and paths that escape it."""
    import io

    destination = Path(destination)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            _extract_archive(archive, destination, commit)
    except DesktopError:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    except zipfile.BadZipFile:
        shutil.rmtree(destination, ignore_errors=True)
        raise DesktopError("The update download was not a valid archive.") from None


def _extract_archive(archive: zipfile.ZipFile, destination: Path, commit: str) -> None:
    infos = [info for info in archive.infolist() if info.filename]
    names = [info.filename.replace("\\", "/") for info in infos]
    roots = {name.split("/", 1)[0] for name in names if name and name not in {"/", ""}}
    if len(roots) != 1:
        raise DesktopError("The download was not a single Align project.")
    root_name = next(iter(roots))
    if commit[:7] not in root_name:
        raise DesktopError("The download was not the Align commit that was requested.")
    total = 0
    for info in infos:
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or (len(name) >= 2 and name[1] == ":"):
            raise DesktopError("The download contained an unsafe path.")
        if "\x00" in name or len(name) > 240:
            raise DesktopError("The download contained an unsafe path.")
        parts = [part for part in name.split("/") if part not in {"", "."}]
        if any(part == ".." for part in parts):
            raise DesktopError("The download contained an unsafe path.")
        if _member_is_link(info):
            raise DesktopError("The download contained a link, which Align will not follow.")
        if info.file_size > MAX_MEMBER_BYTES:
            raise DesktopError("The update download was larger than Align will accept.")
        total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise DesktopError("The update download was larger than Align will accept.")
    for info in infos:
        name = info.filename.replace("\\", "/")
        if not name.startswith(root_name + "/"):
            continue
        relative = name[len(root_name) + 1 :]
        if not relative or relative.endswith("/") or _skipped(relative):
            continue
        target = destination.joinpath(*relative.split("/"))
        if not _inside_destination(target, destination):
            raise DesktopError("The download contained an unsafe path.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)
        if not _inside_destination(target, destination):
            raise DesktopError("The download contained an unsafe path.")
    problem = tree_problems(destination)
    if problem:
        raise DesktopError(problem)
    write_manifest(destination, commit, awaiting_health=True)


def _inside_destination(path: Path, destination: Path) -> bool:
    try:
        path.resolve().relative_to(destination.resolve())
    except (OSError, ValueError):
        return False
    return True


def describe(data_dir: Path, store: SecretStore | None = None) -> dict:
    data_dir = Path(data_dir)
    preferences = load_preferences(data_dir)
    stored = load_status(data_dir)
    keeper = store if store is not None else default_store(data_dir)
    try:
        token_saved = bool(keeper.load())
    except OSError:
        token_saved = False
    local = installed_commit(data_dir)
    remote = _sha(stored.get("remote_commit"))
    incoming = data_dir / INCOMING_NAME
    staged = _sha((read_manifest(incoming) or {}).get("commit")) if incoming.is_dir() else ""
    available = bool(local and remote and local != remote)
    return {
        "ok": True,
        "installed_commit": local,
        "remote_commit": remote,
        "staged_commit": staged,
        "update_available": available,
        "install_offered": bool(remote) and (available or not local or (staged and staged != local)),
        "restart_required": bool(staged and staged != local),
        "check_on_launch": preferences["check_on_launch"],
        "token_saved": token_saved,
        "code_source": "override" if os.environ.get("ALIGN_APP_CODE") else "bundled",
        "branch": BRANCH,
        "summary": str(stored.get("summary") or ""),
        "error": str(stored.get("error") or ""),
    }


def check_for_update(
    data_dir: Path,
    *,
    transport: GithubTransport | None = None,
    store: SecretStore | None = None,
) -> dict:
    """Compare the installed commit with GitHub. This does not download code."""
    data_dir = Path(data_dir)
    keeper = store if store is not None else default_store(data_dir)
    token = keeper.load()
    client = transport or GithubTransport()
    try:
        remote = client.commit(token)
    except DesktopError as error:
        _write_status(data_dir, error=str(error), summary=str(error))
        raise
    local = installed_commit(data_dir)
    if local and local == remote:
        summary = "Already up to date."
    elif local:
        summary = f"An update is available ({remote[:7]})."
    else:
        summary = f"The latest Align commit is {remote[:7]}. This programme has no recorded commit."
    _write_status(
        data_dir,
        remote_commit=remote,
        checked_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        error="",
        summary=summary,
    )
    result = describe(data_dir, keeper)
    result["summary"] = summary
    result["remote_commit"] = remote
    result["update_available"] = bool(local and local != remote)
    result["install_offered"] = bool(local != remote)
    return result


def _incoming_commit(data_dir: Path) -> str:
    payload = read_manifest(Path(data_dir) / INCOMING_NAME)
    if tree_problems(Path(data_dir) / INCOMING_NAME) or manifest_problems(payload):
        return ""
    return _sha((payload or {}).get("commit"))


def apply_update(
    data_dir: Path,
    *,
    transport: GithubTransport | None = None,
    store: SecretStore | None = None,
) -> dict:
    """Download the checked commit into app-code.incoming. The running code stays put."""
    data_dir = Path(data_dir)
    with _APPLY_LOCK:
        keeper = store if store is not None else default_store(data_dir)
        client = transport or GithubTransport()
        token = keeper.load()
        remote = client.commit(token)
        local = installed_commit(data_dir)
        if local and local == remote:
            summary = "Already up to date."
            _write_status(data_dir, remote_commit=remote, error="", summary=summary)
            result = describe(data_dir, keeper)
            result.update({"changed": False, "restart_required": False, "summary": summary, "remote_commit": remote})
            return result
        if _incoming_commit(data_dir) == remote:
            summary = f"Commit {remote[:7]} is ready. Restart Align to load it. Planner data was not changed."
        else:
            payload = client.zipball(remote, token)
            extract_zip(payload, data_dir / INCOMING_NAME, remote)
            summary = f"Commit {remote[:7]} is ready. Restart Align to load it. Planner data was not changed."
        _write_status(data_dir, remote_commit=remote, error="", summary=summary)
        result = describe(data_dir, keeper)
        result.update({
            "changed": True,
            "restart_required": True,
            "summary": summary,
            "remote_commit": remote,
            "staged_commit": remote,
        })
        return result


def apply_installed_update(data_dir: Path | None = None) -> dict:
    """Entry used by the installed programme, including the Studio Updates button."""
    from desktop.paths import user_data_dir

    return apply_update(Path(data_dir) if data_dir is not None else user_data_dir())


def maybe_check_on_launch(data_dir: Path) -> None:
    """When the person asked, compare versions in the background. Do not download."""
    if not load_preferences(data_dir)["check_on_launch"]:
        return

    def run() -> None:
        try:
            check_for_update(data_dir)
        except DesktopError as error:
            try:
                _write_status(data_dir, error=str(error), summary=str(error))
            except OSError:
                return
        except OSError:
            return

    threading.Thread(target=run, name="AlignUpdateCheck", daemon=True).start()


def restart_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--serve"]
    return [sys.executable, "-m", "desktop", "--serve"]


def restart_environment() -> dict[str, str]:
    """Environment for the replacement process.

    ALIGN_APP_CODE is omitted so the new process validates the download itself.
    """
    env = os.environ.copy()
    env.pop("ALIGN_APP_CODE", None)
    return env


def restart_cwd() -> str:
    from desktop.app_code import programme_root

    return str(programme_root())


def _port_free(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def schedule_restart(server) -> None:
    """Answer the current request, then start the programme again.

    The new process loads app-code after the download has been staged. Planner
    data is not part of that process.
    """
    try:
        port = int(server.server_address[1])
    except (AttributeError, TypeError, ValueError, IndexError):
        raw = os.environ.get("ALIGN_PORT", "8001").strip() or "8001"
        port = int(raw)

    def go() -> None:
        import time

        time.sleep(0.4)
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
        for _ in range(50):
            if _port_free(port):
                break
            time.sleep(0.1)
        kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(restart_command(), cwd=restart_cwd(), env=restart_environment(), **kwargs)  # noqa: S603
        os._exit(0)

    threading.Thread(target=go, name="AlignUpdateRestart", daemon=False).start()


"""Safe local checks for the installed programme's code update.

These tests do not contact GitHub, git, or a production database.
"""
from __future__ import annotations

import io
import json
import os
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

import desktop
from align_paths import source_root
from desktop.app_code import consider_override, mark_override_healthy, prepare_runtime, promote_incoming, write_manifest
from desktop.errors import DesktopError
from desktop.secrets import MemorySecretStore, UnavailableSecretStore, seal_token
from desktop.update import (
    _GithubRedirect,
    apply_update,
    assert_github_https,
    check_for_update,
    extract_zip,
    maybe_check_on_launch,
    restart_command,
    restart_environment,
)
from desktop.update_http import handle_update

COMMIT_A = "a" * 40
COMMIT_B = "b" * 40
TOKEN = "github_pat_aligndesktop"


def project_zip(commit: str = COMMIT_B, *, slip: bool = False, link: bool = False) -> bytes:
    buffer = io.BytesIO()
    root = f"wjb006-Align-V3.0-{commit[:7]}"
    with zipfile.ZipFile(buffer, "w") as archive:
        if slip:
            archive.writestr(f"{root}/../../escape.py", "print('no')\n")
        elif link:
            info = zipfile.ZipInfo(f"{root}/app.py")
            info.external_attr = (0o120777) << 16
            archive.writestr(info, "print('no')\n")
        else:
            files = {
                "app.py": "BUILD = 1\n",
                "align_paths.py": "ROOT = '.'\n",
                "static/desktop.html": "<!doctype html><title>Align</title>\n",
                "static/index.html": "<!doctype html><title>Planner</title>\n",
                "desktop/auth.py": "AUTH = True\n",
                "static/desktop-login.html": "<!doctype html><title>Login</title>\n",
                "static/desktop-login.css": "body {}\n",
                "static/desktop-login.js": "window.login = true;\n",
                "migrations/001_test.sql": "SELECT 1;\n",
                "nested/planner.sqlite3": "not-the-planner",
            }
            for name, content in files.items():
                archive.writestr(f"{root}/{name}", content)
    return buffer.getvalue()


def write_tree(root: Path, commit: str, *, awaiting: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("BUILD = 1\n", encoding="utf-8")
    (root / "align_paths.py").write_text("ROOT = '.'\n", encoding="utf-8")
    (root / "static").mkdir(exist_ok=True)
    (root / "static" / "desktop.html").write_text("<!doctype html><title>Align</title>\n", encoding="utf-8")
    (root / "static" / "index.html").write_text("<!doctype html><title>Planner</title>\n", encoding="utf-8")
    (root / "desktop").mkdir(exist_ok=True)
    (root / "desktop" / "auth.py").write_text("AUTH = True\n", encoding="utf-8")
    (root / "static" / "desktop-login.html").write_text("<!doctype html><title>Login</title>\n", encoding="utf-8")
    (root / "static" / "desktop-login.css").write_text("body {}\n", encoding="utf-8")
    (root / "static" / "desktop-login.js").write_text("window.login = true;\n", encoding="utf-8")
    (root / "migrations").mkdir(exist_ok=True)
    (root / "migrations" / "001_test.sql").write_text("SELECT 1;\n", encoding="utf-8")
    write_manifest(root, commit, awaiting_health=awaiting)


class FakeGithub:
    def __init__(self, commit: str, payload: bytes) -> None:
        self.commit_sha = commit
        self.payload = payload
        self.zips = 0
        self.token = ""

    def commit(self, token: str) -> str:
        self.token = token
        return self.commit_sha

    def zipball(self, sha: str, token: str) -> bytes:
        self.zips += 1
        self.token = token
        return self.payload


class Handler:
    def __init__(self, path: str, command: str = "GET", body: bytes = b"", client: str = "127.0.0.1", origin: str | None = None) -> None:
        self.path = path
        self.command = command
        self.client_address = (client, 9)
        self.headers = {"Host": "127.0.0.1:8001", "Content-Length": str(len(body))}
        if origin is not None:
            self.headers["Origin"] = origin
        self.rfile = io.BytesIO(body)
        self.server = ("restart-should-be-patched",)
        self.sent = None

    def send_json(self, status: int, payload: dict) -> None:
        self.sent = (status, payload)


class DesktopUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = os.environ.copy()
        self.path = sys.path[:]
        self.package_path = list(desktop.__path__)
        self.modules = dict(sys.modules)
        self.temporary = tempfile.TemporaryDirectory()
        self.data = Path(self.temporary.name)
        os.environ["ALIGN_DATA_DIR"] = str(self.data)
        self.git = patch("desktop.update.read_git_head", return_value="")
        self.git.start()

    def tearDown(self) -> None:
        self.git.stop()
        sys.path[:] = self.path
        desktop.__path__[:] = self.package_path
        for name in list(sys.modules):
            if name not in self.modules:
                del sys.modules[name]
        for name, module in self.modules.items():
            sys.modules[name] = module
        os.environ.clear()
        os.environ.update(self.environment)
        self.temporary.cleanup()

    def test_github_downloads_stay_on_https(self) -> None:
        assert_github_https("https://api.github.com/repos/wjb006/Align-V3.0/commits/codex/align-v3-rebuild")
        assert_github_https("https://codeload.github.com/wjb006/Align-V3.0/legacy.zip/abcd")
        for url in (
            "http://api.github.com/repos/wjb006/Align-V3.0/zipball/aaaaaaaa",
            "https://example.test/archive.zip",
            "https://token@api.github.com/repos/wjb006/Align-V3.0/zipball/aaaaaaaa",
        ):
            with self.assertRaises(DesktopError):
                assert_github_https(url)
        handler = _GithubRedirect()
        request = Request("https://api.github.com/repos/wjb006/Align-V3.0/zipball/" + COMMIT_B)
        with self.assertRaises(DesktopError):
            handler.redirect_request(request, None, 302, "Found", {}, "https://example.test/archive.zip")
        allowed = handler.redirect_request(
            request, None, 302, "Found", {}, "https://codeload.github.com/wjb006/Align-V3.0/zip/" + COMMIT_B
        )
        self.assertTrue(allowed.full_url.startswith("https://codeload.github.com/"))

    def test_check_compares_commits_and_does_not_download(self) -> None:
        with patch("desktop.update.read_git_head", return_value=COMMIT_A):
            transport = FakeGithub(COMMIT_B, project_zip())
            result = check_for_update(self.data, transport=transport, store=MemorySecretStore())
        self.assertEqual(transport.zips, 0)
        self.assertTrue(result["update_available"])
        self.assertEqual(result["installed_commit"], COMMIT_A)
        self.assertEqual(result["remote_commit"], COMMIT_B)
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_download_is_staged_without_touching_planner_data_or_git(self) -> None:
        database = self.data / "align.sqlite3"
        database.write_bytes(b"planner-bytes")
        transport = FakeGithub(COMMIT_B, project_zip())
        with patch("desktop.update.subprocess.run", side_effect=AssertionError("git")):
            with patch("desktop.update.read_git_head", return_value=COMMIT_A):
                result = apply_update(self.data, transport=transport, store=MemorySecretStore())
        self.assertEqual(database.read_bytes(), b"planner-bytes")
        self.assertEqual(transport.zips, 1)
        self.assertTrue(result["restart_required"])
        self.assertFalse((self.data / "app-code").exists())
        incoming = self.data / "app-code.incoming"
        self.assertTrue((incoming / "app.py").is_file())
        self.assertEqual(list(incoming.rglob("*.sqlite3")), [])
        manifest = json.loads((incoming / "align-update.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["commit"], COMMIT_B)
        self.assertEqual(manifest["repo"], "wjb006/Align-V3.0")
        self.assertEqual(manifest["branch"], "codex/align-v3-rebuild")
        self.assertTrue(manifest["awaiting_health"])
        self.assertNotIn("git", result["summary"])

    def test_current_commit_is_not_downloaded_again(self) -> None:
        transport = FakeGithub(COMMIT_A, project_zip(COMMIT_A))
        with patch("desktop.update.read_git_head", return_value=COMMIT_A):
            result = apply_update(self.data, transport=transport, store=MemorySecretStore())
        self.assertEqual(transport.zips, 0)
        self.assertFalse(result["changed"])
        self.assertFalse((self.data / "app-code.incoming").exists())

    def test_unsafe_archive_is_rejected_and_removed(self) -> None:
        for payload, message in (
            (project_zip(slip=True), "unsafe path"),
            (project_zip(link=True), "will not follow"),
        ):
            with self.assertRaisesRegex(DesktopError, message):
                extract_zip(payload, self.data / "app-code.incoming", COMMIT_B)
            self.assertFalse((self.data / "app-code.incoming").exists())
        self.assertTrue(stat.S_ISLNK(0o120777))

    def test_valid_override_is_loaded_and_a_failed_one_falls_back(self) -> None:
        write_tree(self.data / "app-code", COMMIT_B, awaiting=False)
        (self.data / "app-code" / "keep.txt").write_text("current", encoding="utf-8")
        write_tree(self.data / "app-code.incoming", COMMIT_A, awaiting=True)
        self.assertEqual(consider_override(self.data), (self.data / "app-code").resolve())
        self.assertEqual(json.loads((self.data / "app-code" / "align-update.json").read_text(encoding="utf-8"))["commit"], COMMIT_B)
        self.assertTrue((self.data / "app-code.incoming").is_dir())
        self.assertFalse((self.data / "app-code.attempt").exists())
        self.assertTrue(promote_incoming(self.data))
        self.assertEqual((self.data / "app-code.previous" / "keep.txt").read_text(encoding="utf-8"), "current")
        self.assertEqual(json.loads((self.data / "app-code" / "align-update.json").read_text(encoding="utf-8"))["commit"], COMMIT_A)
        self.assertIsNone(consider_override(self.data))
        loaded = consider_override(self.data, commit=True)
        self.assertEqual(loaded, (self.data / "app-code").resolve())
        self.assertTrue((self.data / "app-code.attempt").is_file())
        mark_override_healthy(self.data)
        self.assertFalse(json.loads((self.data / "app-code" / "align-update.json").read_text(encoding="utf-8"))["awaiting_health"])
        self.assertFalse((self.data / "app-code.attempt").exists())
        os.environ["ALIGN_APP_CODE"] = str(self.data / "app-code")
        self.assertEqual(source_root(), (self.data / "app-code").resolve())
        os.environ.pop("ALIGN_APP_CODE")
        write_manifest(self.data / "app-code", COMMIT_A, awaiting_health=True)
        (self.data / "app-code.attempt").write_text(COMMIT_A, encoding="utf-8")
        self.assertIsNone(consider_override(self.data))
        self.assertTrue((self.data / "app-code").is_dir())
        self.assertIsNone(consider_override(self.data, commit=True))
        self.assertFalse((self.data / "app-code").exists())
        self.assertTrue(any(path.name.startswith("app-code.rejected-") for path in self.data.iterdir()))
        self.assertTrue((self.data / "app-code.previous").is_dir())
        self.assertNotEqual(source_root(), self.data / "app-code.previous")

    def test_incomplete_or_linked_override_uses_the_bundled_code(self) -> None:
        incoming = self.data / "app-code.incoming"
        incoming.mkdir()
        (incoming / "note.txt").write_text("partial", encoding="utf-8")
        current = self.data / "app-code"
        current.mkdir()
        (current / "keep.txt").write_text("keep", encoding="utf-8")
        self.assertIsNone(consider_override(self.data))
        self.assertTrue(incoming.exists())
        self.assertIsNone(consider_override(self.data, commit=True))
        self.assertFalse(incoming.exists())
        self.assertEqual((current / "keep.txt").read_text(encoding="utf-8"), "keep")
        write_tree(current, COMMIT_B, awaiting=False)
        real = self.data / "real-app.py"
        real.write_text("BUILD = 1\n", encoding="utf-8")
        (current / "app.py").unlink()
        try:
            (current / "app.py").symlink_to(real)
        except OSError as error:
            if getattr(error, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege is not enabled; archive-link rejection is covered separately.")
            raise
        self.assertIsNone(consider_override(self.data))
        os.environ["ALIGN_APP_CODE"] = str(current)
        self.assertNotEqual(source_root(), current.resolve())

    def test_prepare_runtime_can_be_called_twice_without_discarding_the_update(self) -> None:
        write_tree(self.data / "app-code", COMMIT_B, awaiting=False)
        first = prepare_runtime()
        second = prepare_runtime()
        self.assertEqual(first, second)
        self.assertTrue((self.data / "app-code" / "app.py").is_file())
        self.assertEqual(os.environ["ALIGN_APP_CODE"], str((self.data / "app-code").resolve()))

    def test_token_is_not_written_in_plain_text(self) -> None:
        store = MemorySecretStore()
        body = json.dumps({"check_on_launch": True, "token": TOKEN}).encode()
        handler = Handler("/api/desktop/update/settings", "POST", body)
        self.assertTrue(handle_update(handler, data_dir=self.data, store=store))
        self.assertEqual(handler.sent[0], 200)
        preferences = (self.data / "desktop-update.json").read_text(encoding="utf-8")
        self.assertNotIn(TOKEN, preferences)
        self.assertNotIn(TOKEN, json.dumps(handler.sent[1]))
        self.assertTrue(handler.sent[1]["token_saved"])
        self.assertEqual(store.load(), TOKEN)
        with self.assertRaises(DesktopError):
            seal_token(TOKEN, lambda raw: raw)
        sealed = seal_token(TOKEN, lambda raw: b"\x01sealed")
        self.assertNotIn(TOKEN.encode(), sealed)
        refused = Handler("/api/desktop/update/settings", "POST", body)
        self.assertTrue(handle_update(refused, data_dir=self.data, store=UnavailableSecretStore()))
        self.assertEqual(refused.sent[0], 400)
        self.assertNotIn(TOKEN, (self.data / "desktop-update.json").read_text(encoding="utf-8"))

    def test_update_routes_are_local_and_a_launch_check_does_not_download(self) -> None:
        remote = Handler("/api/desktop/update", client="10.1.1.1")
        handle_update(remote, data_dir=self.data, store=MemorySecretStore())
        self.assertEqual(remote.sent[0], 403)
        foreign = Handler("/api/desktop/update", origin="https://example.test")
        handle_update(foreign, data_dir=self.data, store=MemorySecretStore())
        self.assertEqual(foreign.sent[0], 403)
        with patch("desktop.update.threading.Thread") as thread:
            maybe_check_on_launch(self.data)
        thread.assert_not_called()
        transport = FakeGithub(COMMIT_B, project_zip())
        checked = Handler("/api/desktop/update/check", "POST", b"{}")
        handle_update(checked, data_dir=self.data, store=MemorySecretStore(), transport=transport)
        self.assertEqual(checked.sent[0], 200)
        self.assertEqual(transport.zips, 0)

    def test_restart_uses_the_programme_and_not_git(self) -> None:
        os.environ["ALIGN_APP_CODE"] = str(self.data / "app-code")
        self.assertNotIn("ALIGN_APP_CODE", restart_environment())
        self.assertEqual(restart_command(), [sys.executable, "-m", "desktop", "--serve"])
        previous = getattr(sys, "frozen", None)
        executable = sys.executable
        sys.frozen = True
        sys.executable = r"C:\Align\Align.exe"
        try:
            self.assertEqual(restart_command(), [r"C:\Align\Align.exe", "--serve"])
        finally:
            sys.executable = executable
            if previous is None:
                del sys.frozen
            else:
                sys.frozen = previous
        self.assertNotIn("git", restart_command())


if __name__ == "__main__":
    unittest.main()

"""Desktop programme: data stays put, the server is recognisable, and the home screen opens."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import studio_update
from align_paths import source_root
from desktop.errors import DesktopError
from desktop.launch import main
from desktop.paths import legacy_database_candidates, user_data_dir
from desktop.persistence import adopt_database, content_score, inspect_database
from desktop.supervisor import fetch_health, free_port, is_align_health, start_server
from desktop.window import windows_app_command


def make_align_db(path: Path, events: int = 0, user_name: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE settings(setting_key TEXT PRIMARY KEY, setting_value TEXT)")
    connection.execute("CREATE TABLE organiser_sections(id INTEGER PRIMARY KEY, name TEXT)")
    connection.execute("CREATE TABLE organiser_events(id INTEGER PRIMARY KEY, title TEXT)")
    connection.execute("CREATE TABLE builder_records(id INTEGER PRIMARY KEY)")
    if user_name:
        connection.execute("INSERT INTO settings(setting_key, setting_value) VALUES('user_name', ?)", (user_name,))
    for index in range(events):
        connection.execute("INSERT INTO organiser_events(title) VALUES(?)", (f"Event {index}",))
    connection.commit()
    connection.close()


class DesktopPersistenceTests(unittest.TestCase):
    def test_user_data_dir_honours_the_override(self):
        with patch.dict(os.environ, {"ALIGN_DATA_DIR": "/tmp/align-data"}):
            self.assertEqual(user_data_dir(), Path("/tmp/align-data"))

    def test_existing_planner_data_is_not_replaced(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            current = base / "data" / "align.sqlite3"
            legacy = base / "old" / "align.sqlite3"
            make_align_db(current, events=2, user_name="Will")
            make_align_db(legacy, events=5, user_name="Older")
            before = current.read_bytes()
            result = adopt_database(current.parent, [legacy])
            self.assertEqual(result["action"], "kept")
            self.assertEqual(current.read_bytes(), before)
            self.assertTrue(legacy.is_file())
            self.assertEqual(content_score(current), 3)

    def test_legacy_database_is_copied_once_and_left_in_place(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            legacy = base / "app" / "align.sqlite3"
            make_align_db(legacy, events=1, user_name="Kept")
            result = adopt_database(base / "data", [legacy])
            self.assertEqual(result["action"], "copied")
            self.assertEqual(content_score(result["database"]), 2)
            self.assertTrue(legacy.is_file())
            self.assertEqual(content_score(legacy), 2)

    def test_blank_database_gives_way_to_a_real_legacy_copy(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            current = base / "data" / "align.sqlite3"
            legacy = base / "install" / "app" / "align.sqlite3"
            make_align_db(current, events=0)
            make_align_db(legacy, events=2)
            result = adopt_database(current.parent, [legacy])
            self.assertEqual(result["action"], "copied")
            self.assertEqual(content_score(current), 2)
            self.assertTrue(legacy.is_file())
            quarantined = list(current.parent.glob("align.sqlite3.blank-*"))
            self.assertEqual(len(quarantined), 1)
            self.assertTrue(quarantined[0].is_file())

    def test_unreadable_database_is_moved_aside(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            current = base / "data" / "align.sqlite3"
            current.parent.mkdir()
            current.write_bytes(b"this is not a database")
            legacy = base / "legacy" / "align.sqlite3"
            make_align_db(legacy, events=1)
            plan = inspect_database(current.parent, [legacy])
            self.assertEqual(plan["action"], "replace-unreadable")
            result = adopt_database(current.parent, [legacy])
            self.assertEqual(result["action"], "copied")
            self.assertTrue(legacy.is_file())
            self.assertEqual(content_score(current), 1)
            self.assertTrue(list(current.parent.glob("align.sqlite3.unreadable-*")))

    def test_corrupt_legacy_file_is_ignored(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            junk = base / "align.sqlite3"
            junk.write_bytes(b"nope")
            result = adopt_database(base / "data", [junk])
            self.assertEqual(result["action"], "create-on-start")
            self.assertFalse(result["database"].exists())
            self.assertTrue(junk.is_file())

    def test_dry_run_does_not_copy_or_start(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / "data"
            env = {
                "ALIGN_DATA_DIR": str(data),
                "ALIGN_LEGACY_DATABASES": "",
                "ALIGN_PORT": str(free_port()),
            }
            with patch.dict(os.environ, env, clear=False):
                code = main(["--dry-run"])
            self.assertEqual(code, 0)
            self.assertFalse(data.exists())


class DesktopLaunchTests(unittest.TestCase):
    def test_health_recognises_align(self):
        self.assertTrue(is_align_health({"version": {"build": 156, "app": "3.0"}}))
        self.assertFalse(is_align_health({"status": "ok"}))
        self.assertFalse(is_align_health({"version": {"build": 0, "app": "3.0"}}))

    def test_windows_window_is_a_large_app_window(self):
        edge = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        command, args = windows_app_command(
            "http://127.0.0.1:8001/desktop",
            exists=lambda path: path == edge,
            candidates=[r"C:\missing\chrome.exe", edge],
        )
        self.assertEqual(command, edge)
        self.assertIn("--app=http://127.0.0.1:8001/desktop", args)
        self.assertIn("--window-size=1360,900", args)

    def test_windows_window_falls_back_to_the_default_browser(self):
        command, args = windows_app_command(
            "http://127.0.0.1:8001/desktop",
            exists=lambda path: False,
            candidates=[r"C:\missing\msedge.exe"],
        )
        self.assertEqual(command, "rundll32")
        self.assertEqual(args[0], "url.dll,FileProtocolHandler")

    def test_frozen_source_root_uses_the_bundle(self):
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            previous = getattr(sys, "frozen", None)
            previous_meipass = getattr(sys, "_MEIPASS", None)
            sys.frozen = True
            sys._MEIPASS = folder
            try:
                self.assertEqual(source_root(), Path(folder).resolve())
            finally:
                if previous is None:
                    del sys.frozen
                else:
                    sys.frozen = previous
                if previous_meipass is None:
                    if hasattr(sys, "_MEIPASS"):
                        del sys._MEIPASS
                else:
                    sys._MEIPASS = previous_meipass

    def test_packaged_update_keeps_data_and_does_not_call_git(self):
        import sys
        called = []
        previous = getattr(sys, "frozen", None)
        sys.frozen = True
        try:
            with patch.object(studio_update, "_git", side_effect=lambda *args: called.append(args)):
                with self.assertRaisesRegex(RuntimeError, "Windows package"):
                    studio_update.update_from_github(lambda: called.append("database"))
        finally:
            if previous is None:
                del sys.frozen
            else:
                sys.frozen = previous
        self.assertEqual(called, [])

    def test_other_programme_on_the_port_is_reported(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'{"status":"ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            ready, responding = fetch_health(server.server_port)
            self.assertFalse(ready)
            self.assertTrue(responding)
            with self.assertRaises(DesktopError) as caught:
                start_server(Path(self.id()), server.server_port, wait_seconds=1)
            self.assertIn("not Align", str(caught.exception))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_desktop_home_planner_and_studio_answer(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            env = {
                "ALIGN_DATA_DIR": folder,
                "ALIGN_LEGACY_DATABASES": "",
                "ALIGN_BETA_MODE": "0",
            }
            port = free_port()
            with patch.dict(os.environ, env, clear=False):
                handle = start_server(Path(folder), port, wait_seconds=40)
            self.addCleanup(handle.stop)
            base = f"http://127.0.0.1:{handle.port}"

            def get(path):
                with urllib.request.urlopen(base + path, timeout=10) as response:
                    return response.status, dict(response.headers), response.read()

            status, headers, home = get("/desktop")
            self.assertEqual(status, 200)
            self.assertIn(b"Planner and Management Studio", home)
            self.assertIn(b'href="/"', home)
            self.assertIn(b'href="/management-studio"', home)
            self.assertEqual(headers["X-Frame-Options"], "DENY")

            status, headers, planner = get("/")
            self.assertEqual(status, 200)
            self.assertIn(b"Align V3.0", planner)
            self.assertEqual(headers["X-Frame-Options"], "SAMEORIGIN")

            status, headers, health_body = get("/api/health")
            health = json.loads(health_body)
            self.assertEqual(status, 200)
            self.assertEqual(health["version"]["app"], "3.0")
            self.assertEqual(health["database"]["integrity"], "ok")
            self.assertEqual(headers["X-Frame-Options"], "DENY")

            status, _, status_body = get("/api/desktop/status")
            desktop_status = json.loads(status_body)
            self.assertEqual(status, 200)
            self.assertTrue(desktop_status["database_present"])
            self.assertFalse(desktop_status["hosted_checked"])
            self.assertNotIn("sqlite", json.dumps(desktop_status).lower())
            joined = json.dumps(desktop_status)
            self.assertNotIn(folder, joined)

            status, _, boot = get("/api/bootstrap")
            self.assertEqual(status, 200)
            bootstrap = json.loads(boot)
            self.assertEqual(bootstrap["dashboard"]["alerts"], [])
            self.assertIn("upcoming_events", bootstrap["dashboard"])

            status, _, studio = get("/management-studio")
            self.assertEqual(status, 200)
            self.assertIn(b"Management Studio", studio)
            self.assertIn(b"Working calendar", studio)
            self.assertIn(b"Host overview", studio)
            self.assertIn(b"management-studio-nav.js", studio)

    def test_fresh_database_dashboard_skips_missing_legacy_alerts(self):
        import tempfile
        import app
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "align.sqlite3"
            with patch.object(app, "DATABASE", database):
                app.initialise_database()
                with app.db_connection() as connection:
                    self.assertIsNone(connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alerts'"
                    ).fetchone())
                    payload = app.dashboard(connection)
        self.assertEqual(payload["alerts"], [])
        self.assertIsInstance(payload["upcoming_events"], list)

    def test_legacy_shift_alerts_still_load(self):
        import sqlite3
        import tempfile
        from datetime import datetime, timedelta
        import app
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "align.sqlite3"
            with patch.object(app, "DATABASE", database):
                app.initialise_database()
                when = (datetime.now() + timedelta(days=1)).replace(microsecond=0).isoformat(timespec="minutes")
                with sqlite3.connect(database) as connection:
                    connection.execute(
                        """CREATE TABLE alerts (
                            id INTEGER PRIMARY KEY, shift_id INTEGER NOT NULL, title TEXT NOT NULL,
                            alert_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending')"""
                    )
                    connection.execute(
                        """CREATE TABLE alert_rules (
                            id INTEGER PRIMARY KEY, title TEXT NOT NULL,
                            minutes_before INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1)"""
                    )
                    connection.execute(
                        """INSERT INTO shifts(work_date,location_name,shift_type_name,colour,start_time,end_time,hours)
                           VALUES('2026-10-28','Lime Street','Early','#365CE6','09:00','17:00',8)"""
                    )
                    shift_id = connection.execute("SELECT id FROM shifts").fetchone()[0]
                    connection.execute(
                        "INSERT INTO alerts(shift_id,title,alert_at,status) VALUES(?,?,?,'pending')",
                        (shift_id, "Leave home", when),
                    )
                    connection.execute(
                        "INSERT INTO alert_rules(title,minutes_before,active) VALUES('Before',30,1)"
                    )
                with app.db_connection() as connection:
                    payload = app.dashboard(connection)
                    rules = app.calendar_data(connection)["alert_rules"]
        self.assertEqual([item["title"] for item in payload["alerts"]], ["Leave home"])
        self.assertEqual(rules[0]["title"], "Before")

    def test_legacy_override_can_disable_adoption(self):
        with patch.dict(os.environ, {"ALIGN_LEGACY_DATABASES": ""}):
            self.assertEqual(legacy_database_candidates(), [])


class DesktopStatusGuardTests(unittest.TestCase):
    def test_desktop_status_rejects_remote_clients(self):
        from desktop.status import handle_status

        class Handler:
            client_address = ("203.0.113.8", 4400)

            def send_json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = Handler()
        handle_status(handler)
        self.assertEqual(handler.status, 403)


class InstallerGuardTests(unittest.TestCase):
    def test_windows_installer_does_not_delete_the_database(self):
        text = (Path(__file__).resolve().parent / "installer" / "windows" / "Install-Align-Studio.ps1").read_text(encoding="utf-8")
        self.assertNotIn("Remove-Item $ExistingDatabase", text)
        self.assertNotIn("Remove-Item $ExistingDatabase -Force", text)
        self.assertIn("never deletes", text.lower())
        self.assertIn("Align.exe", text)


if __name__ == "__main__":
    unittest.main()

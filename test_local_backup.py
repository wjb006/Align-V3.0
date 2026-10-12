"""Local SQLite backup and restore tests use an isolated database."""
import json
import sqlite3
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app
from test_support import IsolatedAppServer


class LocalBackupTests(unittest.TestCase):
    setUp = IsolatedAppServer.setUp
    tearDown = IsolatedAppServer.tearDown
    request = IsolatedAppServer.request
    json_request = IsolatedAppServer.json_request

    def binary_request(self, method, path, body, headers):
        client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        client.request(method, path, body=body, headers=headers)
        response = client.getresponse()
        result = (response.status, response.read())
        client.close()
        return result

    def test_download_returns_private_sqlite_snapshot(self):
        status, headers, body = self.request("GET", "/api/local-backup")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn('attachment; filename="align-backup-', headers["Content-Disposition"])
        self.assertTrue(body.startswith(b"SQLite format 3\x00"))

    def test_download_requires_the_local_admin_session(self):
        original_password = app.ADMIN_PASSWORD
        app.ADMIN_PASSWORD = "test-admin-password"
        token = "local-backup-test-session"
        app.ADMIN_SESSIONS.discard(token)
        try:
            self.assertEqual(self.request("GET", "/api/local-backup")[0], 403)
            app.ADMIN_SESSIONS.add(token)
            status, _, body = self.request("GET", "/api/local-backup", headers={"X-Align-Admin": token})
            self.assertEqual(status, 200, body[:200])
        finally:
            app.ADMIN_PASSWORD = original_password
            app.ADMIN_SESSIONS.discard(token)

    def test_restore_validates_and_keeps_pre_restore_copy(self):
        with app.db_connection() as connection:
            connection.execute("UPDATE settings SET setting_value='Original' WHERE setting_key='user_name'")
        backup = app.local_database_backup(app.DATABASE)
        with app.db_connection() as connection:
            connection.execute("UPDATE settings SET setting_value='Changed' WHERE setting_key='user_name'")

        app.restore_local_database(app.DATABASE, backup)

        with app.db_connection() as connection:
            self.assertEqual(
                connection.execute("SELECT setting_value FROM settings WHERE setting_key='user_name'").fetchone()[0],
                "Original",
            )
        safety_copies = list((Path(app.DATABASE).parent / "Backups").glob("align-pre-restore-*.sqlite3"))
        self.assertEqual(len(safety_copies), 1)
        self.assertTrue(safety_copies[0].read_bytes().startswith(b"SQLite format 3\x00"))

    def test_restore_accepts_v3_backup_without_retired_shift_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "align-v3.sqlite3"
            with sqlite3.connect(candidate) as connection:
                connection.executescript("""
                    CREATE TABLE schema_migrations (migration_id TEXT PRIMARY KEY);
                    CREATE TABLE settings (setting_key TEXT PRIMARY KEY, setting_value TEXT);
                    CREATE TABLE personal_items (id TEXT PRIMARY KEY, kind TEXT, title TEXT);
                    CREATE TABLE organiser_sections (id TEXT PRIMARY KEY, title TEXT);
                """)
            payload = candidate.read_bytes()

        with patch("app.initialise_database_at"):
            app.restore_local_database(app.DATABASE, payload)

        with sqlite3.connect(app.DATABASE) as connection:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        self.assertTrue({"schema_migrations", "settings", "personal_items", "organiser_sections"} <= tables)
        self.assertNotIn("shifts", tables)

    def test_restore_route_accepts_raw_backup_and_reports_safety_copy(self):
        with app.db_connection() as connection:
            connection.execute("UPDATE settings SET setting_value='Before' WHERE setting_key='user_name'")
        backup = app.local_database_backup(app.DATABASE)
        with app.db_connection() as connection:
            connection.execute("UPDATE settings SET setting_value='After' WHERE setting_key='user_name'")

        status, body = self.binary_request(
            "POST",
            "/api/local-backup/restore",
            backup,
            {"Content-Type": "application/vnd.sqlite3"},
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body), {"ok": True, "safety_copy_created": True})
        with app.db_connection() as connection:
            self.assertEqual(
                connection.execute("SELECT setting_value FROM settings WHERE setting_key='user_name'").fetchone()[0],
                "Before",
            )

    def test_restore_is_blocked_while_icloud_is_connected(self):
        backup = app.local_database_backup(app.DATABASE)
        original_manager = app.ICLOUD_MANAGER
        app.ICLOUD_MANAGER = SimpleNamespace(enabled=True, client=object())
        try:
            status, body = self.binary_request(
                "POST",
                "/api/local-backup/restore",
                backup,
                {"Content-Type": "application/vnd.sqlite3"},
            )
        finally:
            app.ICLOUD_MANAGER = original_manager
        self.assertEqual(status, 409)
        self.assertIn(b"Disconnect iCloud", body)

    def test_invalid_restore_leaves_live_database_untouched(self):
        with app.db_connection() as connection:
            connection.execute("UPDATE settings SET setting_value='Keep me' WHERE setting_key='user_name'")
        with self.assertRaisesRegex(ValueError, "not an Align SQLite backup"):
            app.restore_local_database(app.DATABASE, b"not a database")
        with app.db_connection() as connection:
            self.assertEqual(
                connection.execute("SELECT setting_value FROM settings WHERE setting_key='user_name'").fetchone()[0],
                "Keep me",
            )
        self.assertFalse((Path(app.DATABASE).parent / "Backups").exists())

    def test_hosted_mode_rejects_download(self):
        original = app.BETA_MODE
        app.BETA_MODE = True
        try:
            status, _, body = self.request("GET", "/api/local-backup")
        finally:
            app.BETA_MODE = original
        self.assertEqual(status, 403)
        self.assertIn(b"disabled in hosted mode", body)

    def test_request_logs_omit_query_parameters(self):
        handler = SimpleNamespace(log_date_time_string=lambda: "test-date")
        with patch.object(app.LOG, "info") as log:
            app.AlignHandler.log_message(
                handler,
                '"%s" %s %s',
                "GET /api/weather?latitude=51.5&longitude=-3.2 HTTP/1.1",
                "200",
                "10",
            )
        message = " ".join(str(value) for value in log.call_args.args)
        self.assertIn("/api/weather", message)
        self.assertNotIn("latitude", message)
        self.assertNotIn("longitude", message)


if __name__ == "__main__":
    unittest.main()

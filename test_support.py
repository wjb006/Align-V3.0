"""Shared isolated SQLite and HTTP helpers for Align integration tests."""
import gc
import json
import tempfile
import threading
from datetime import date, timedelta
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import app


class QuietHandler(app.AlignHandler):
    def log_message(self, *args):
        pass


class IsolatedAppServer:
    """Mixin for unittest cases that need a private temporary Align database."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="align-test-")
        self.original_database, self.original_password = app.DATABASE, app.ADMIN_PASSWORD
        app.DATABASE = Path(self.temp.name) / "test.sqlite3"
        app.ADMIN_PASSWORD = ""
        app.initialise_database()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.day = (date.today() + timedelta(days=14)).isoformat()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        app.DATABASE, app.ADMIN_PASSWORD = self.original_database, self.original_password
        gc.collect()
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        client.request(method, path, body=json.dumps(data) if data is not None else None,
                       headers={"Content-Type": "application/json", **(headers or {})})
        response = client.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        client.close()
        return result

    def json_request(self, method, path, data=None, expected=None):
        status, _, body = self.request(method, path, data)
        self.assertEqual(status, expected or (201 if method == "POST" else 200), body)
        return json.loads(body)

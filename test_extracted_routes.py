"""Route checks for handlers extracted from app.py."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import app


class ExtractedRouteTests(unittest.TestCase):
    def test_health_settings_admin_sections_and_security_headers(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(app, "DATABASE", Path(folder) / "test.sqlite3"), patch.object(app, "BETA_MODE", False), patch.object(app, "ADMIN_PASSWORD", ""):
            app.initialise_database()
            server = app.AlignServer(("127.0.0.1", 0), app.AlignHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"

            def request(path, body=None, method=None):
                data = json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(
                    base + path,
                    data=data,
                    method=method,
                    headers={"Content-Type": "application/json"} if data is not None else {},
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.status, dict(response.headers), response.read()

            try:
                status, headers, body = request("/api/health")
                self.assertEqual(status, 200)
                health = json.loads(body)
                self.assertEqual(health["version"]["build"], app.BUILD_VERSION)
                self.assertTrue(health["database"]["available"])
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(headers["X-Frame-Options"], "DENY")
                self.assertEqual(headers["Referrer-Policy"], "no-referrer")
                self.assertIn("default-src 'self'", headers["Content-Security-Policy"])

                status, headers, body = request("/")
                self.assertEqual(status, 200)
                self.assertIn(b"V3.0", body)
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                policy = headers["Content-Security-Policy"]
                script_src = next(part.strip() for part in policy.split(";") if part.strip().startswith("script-src"))
                self.assertEqual(script_src, "script-src 'self'")
                self.assertIn("style-src 'self' 'unsafe-inline'", policy)

                with self.assertRaises(urllib.error.HTTPError) as retired_settings:
                    request("/api/settings")
                self.assertEqual(retired_settings.exception.code, 404)

                status, _, body = request(
                    "/api/user-settings", {"user_name": "V3 user"}, "PUT"
                )
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["user_name"], "V3 user")

                status, _, body = request("/api/admin/status")
                self.assertEqual(status, 200)
                self.assertTrue(json.loads(body)["authenticated"])

                status, _, body = request("/api/sections")
                self.assertEqual(status, 200)
                self.assertIsInstance(json.loads(body), list)

                status, _, body = request("/api/admin/login", {"password": ""}, "POST")
                self.assertEqual(status, 200)
                self.assertIn("token", json.loads(body))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_admin_login_rejects_a_wrong_password(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(app, "DATABASE", Path(folder) / "test.sqlite3"), patch.object(app, "BETA_MODE", False), patch.object(app, "ADMIN_PASSWORD", "secret"):
            app.initialise_database()
            server = app.AlignServer(("127.0.0.1", 0), app.AlignHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            req = urllib.request.Request(
                base + "/api/admin/login",
                data=json.dumps({"password": "nope"}).encode(),
                headers={"Content-Type": "application/json"},
            )
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(req, timeout=5)
                self.assertEqual(error.exception.code, 401)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()

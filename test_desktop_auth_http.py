"""HTTP-level checks for the local desktop login gate and persistent cookie."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class DesktopAuthHttpTests(unittest.TestCase):
    def test_login_gate_setup_persistence_and_signout(self):
        script = r'''
import http.client, json, threading
from app import AlignHandler, AlignServer
server = AlignServer(("127.0.0.1", 0), AlignHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
port = server.server_address[1]
host = f"127.0.0.1:{port}"
origin = f"http://{host}"
def request(method, path, body=None, cookie=""):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {}
    if body is not None:
        headers["Content-Type"] = "application/json"
        headers["Origin"] = origin
    if cookie:
        headers["Cookie"] = cookie
    connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    response = connection.getresponse()
    payload = response.read()
    result = (response.status, dict(response.getheaders()), payload)
    connection.close()
    return result
try:
    status, headers, _ = request("GET", "/desktop")
    assert status == 302 and headers.get("Location") == "/desktop-login.html", (status, headers)
    status, _, page = request("GET", "/desktop-login.html")
    assert status == 200 and b"Welcome back" in page, status
    status, _, payload = request("GET", "/api/local-auth/status")
    assert status == 200 and json.loads(payload)["setup_required"] is True, payload
    status, headers, payload = request("POST", "/api/local-auth/setup", {
        "email": "owner@example.com", "display_name": "Owner",
        "password": "a-long-local-password-123", "remember": True,
    })
    assert status == 200, payload
    cookie = headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Max-Age=" in cookie, cookie
    cookie_pair = cookie.split(";", 1)[0]
    status, _, page = request("GET", "/desktop", cookie=cookie_pair)
    assert status == 200 and b"Planner and Management Studio" in page, status
    status, _, payload = request("GET", "/api/local-auth/status", cookie=cookie_pair)
    assert status == 200 and json.loads(payload)["authenticated"] is True, payload
    status, _, payload = request("GET", "/api/admin/status", cookie=cookie_pair)
    assert status == 200 and json.loads(payload)["role"] == "Owner", payload
    status, headers, payload = request("POST", "/api/local-auth/logout", {}, cookie_pair)
    assert status == 200 and "Max-Age=0" in headers.get("Set-Cookie", ""), headers
    status, headers, _ = request("GET", "/desktop")
    assert status == 302 and headers.get("Location") == "/desktop-login.html", (status, headers)
    status, _, payload = request("GET", "/api/admin/status")
    assert status == 401 and json.loads(payload)["code"] == "desktop_login_required", payload
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
'''
        with tempfile.TemporaryDirectory() as folder:
            env = os.environ.copy()
            env.update({
                "ALIGN_STUDIO_LOCAL": "1",
                "ALIGN_LOCAL_LOGIN_ENABLED": "1",
                "ALIGN_BETA_MODE": "0",
                "ALIGN_DATA_DIR": folder,
                "PYTHONPATH": str(ROOT),
            })
            completed = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT, env=env,
                text=True, capture_output=True, timeout=45,
            )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_hosted_beta_auth_is_not_replaced_by_local_desktop_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            env = os.environ.copy()
            env.update({
                "ALIGN_STUDIO_LOCAL": "1",
                "ALIGN_LOCAL_LOGIN_ENABLED": "1",
                "ALIGN_BETA_MODE": "1",
                "ALIGN_DATA_DIR": folder,
                "PYTHONPATH": str(ROOT),
            })
            completed = subprocess.run(
                [sys.executable, "-c", "import app; assert app.BETA_MODE and not app.LOCAL_DESKTOP_MODE"],
                cwd=ROOT, env=env, text=True, capture_output=True, timeout=45,
            )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()

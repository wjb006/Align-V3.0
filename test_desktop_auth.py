"""Persistent local desktop authentication regression tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from desktop.auth import DesktopAuthError, DesktopAuthStore, REMEMBER_SECONDS, SESSION_SECONDS


class DesktopAuthTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.database = Path(self.folder.name) / "desktop-auth.sqlite3"
        self.store = DesktopAuthStore(self.database)

    def tearDown(self):
        self.folder.cleanup()

    def test_first_run_creates_single_local_owner_and_persistent_session(self):
        token, user, expires = self.store.setup(
            "will@example.com", "Will", "a-long-local-password-123", True, now=1_000
        )
        self.assertEqual(user, {"email": "will@example.com", "display_name": "Will", "role": "Owner"})
        self.assertEqual(expires, 1_000 + REMEMBER_SECONDS)
        self.assertEqual(self.store.get_session(token, now=1_001)["role"], "Owner")
        stored = self.database.read_bytes()
        self.assertNotIn(b"a-long-local-password-123", stored)
        self.assertNotIn(token.encode("ascii"), stored)
        restarted = DesktopAuthStore(self.database)
        self.assertEqual(restarted.get_session(token, now=1_002)["email"], "will@example.com")

    def test_remember_disabled_uses_shorter_session_lifetime(self):
        token, _user, expires = self.store.setup(
            "will@example.com", "Will", "a-long-local-password-123", False, now=2_000
        )
        self.assertEqual(expires, 2_000 + SESSION_SECONDS)
        self.assertIsNotNone(self.store.get_session(token, now=2_001))

    def test_login_uses_same_account_and_rejects_wrong_password(self):
        self.store.setup("will@example.com", "Will", "a-long-local-password-123", now=3_000)
        self.assertIsNone(self.store.authenticate("will@example.com", "wrong-password", now=3_001))
        result = self.store.authenticate("WILL@example.com", "a-long-local-password-123", now=3_002)
        self.assertIsNotNone(result)
        self.assertEqual(result[1]["email"], "will@example.com")

    def test_expired_session_is_removed(self):
        token, _user, expires = self.store.setup(
            "will@example.com", "Will", "a-long-local-password-123", True, now=4_000
        )
        self.assertIsNone(self.store.get_session(token, now=expires))
        self.assertIsNone(self.store.get_session(token, now=expires + 1))

    def test_sign_out_revokes_session(self):
        token, _user, _expires = self.store.setup(
            "will@example.com", "Will", "a-long-local-password-123", True, now=5_000
        )
        self.store.revoke(token)
        self.assertIsNone(self.store.get_session(token, now=5_001))

    def test_only_one_owner_account_can_be_created(self):
        self.store.setup("will@example.com", "Will", "a-long-local-password-123", now=6_000)
        with self.assertRaises(DesktopAuthError):
            self.store.setup("other@example.com", "Other", "another-long-password-123", now=6_001)

    def test_short_password_is_rejected(self):
        with self.assertRaises(DesktopAuthError):
            self.store.setup("will@example.com", "Will", "too-short", now=7_000)


if __name__ == "__main__":
    unittest.main()

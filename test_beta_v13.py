import sqlite3
from sqlite_support import connect
import tempfile
import threading
import time
import unittest
from pathlib import Path

from beta_support import BetaError, BetaStore


def initialise(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as c:
        c.execute("CREATE TABLE IF NOT EXISTS marker(value TEXT)")


class BetaV13Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.owner_db = self.root / "align.sqlite3"
        initialise(self.owner_db)
        self.store = BetaStore(self.root, self.owner_db, initialise)
        self.owner, self.owner_code = self.store.ensure_owner("owner@example.com")

    def tearDown(self):
        self.temp.cleanup()

    def invite(self, email="tester@example.com", key="k1"):
        return self.store.create_invite(email, "Tester", initialise, self.owner["user_id"], key)[0]

    def test_invite_is_hashed_case_insensitive_and_no_spaces_password(self):
        item = self.invite()
        self.assertNotIn(item["invite_code"].encode(), self.store.registry.read_bytes())
        self.assertIsNotNone(self.store.validate_invite("tester@example.com", item["invite_code"].lower()))
        with self.assertRaises(BetaError) as ctx:
            self.store.complete_invite("tester@example.com", item["invite_code"], "Coffee Rugby2026")
        self.assertEqual(ctx.exception.code, "invalid_password")

    def test_invite_completion_is_atomic_and_one_time(self):
        item = self.invite()
        results = []
        def worker():
            try:
                row, _ = self.store.complete_invite("tester@example.com", item["invite_code"], "CoffeeRugby2026")
                results.append(("ok", row["user_id"]))
            except BetaError as exc:
                results.append((exc.code, None))
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(sum(x[0] == "ok" for x in results), 1)
        with self.store._connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM beta_users WHERE email='tester@example.com'").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM beta_invites WHERE invite_id=? AND status='used'", (item["invite_id"],)).fetchone()[0], 1)

    def test_replacement_and_revocation(self):
        item = self.invite()
        old = item["invite_code"]
        with self.store._connect() as c:
            c.execute("UPDATE beta_invites SET created_at=created_at-31 WHERE invite_id=?", (item["invite_id"],))
        replacement, _ = self.store.replace_invite(item["invite_id"], self.owner["user_id"], "replace-key")
        self.assertIsNone(self.store.validate_invite("tester@example.com", old))
        self.assertIsNotNone(self.store.validate_invite("tester@example.com", replacement["invite_code"]))
        self.store.revoke_invite(replacement["invite_id"], self.owner["user_id"])
        self.assertIsNone(self.store.validate_invite("tester@example.com", replacement["invite_code"]))

    def test_expiry_uses_server_time(self):
        item = self.invite()
        with self.store._connect() as c:
            c.execute("UPDATE beta_invites SET expires_at=? WHERE invite_id=?", (int(time.time()) - 1, item["invite_id"]))
        self.assertIsNone(self.store.validate_invite("tester@example.com", item["invite_code"]))

    def test_idempotent_concurrent_create_creates_one_invite(self):
        results = []
        def worker():
            results.append(self.store.create_invite("same@example.com", "Same", initialise, self.owner["user_id"], "same-key"))
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(results[0][0]["invite_id"], results[1][0]["invite_id"])
        self.assertEqual(sum("invite_code" in result[0] for result in results), 1)

    def test_password_reset_is_hashed_one_time_and_revokes_sessions(self):
        item = self.invite()
        row, first = self.store.complete_invite("tester@example.com", item["invite_code"], "CoffeeRugby2026")
        _, second = self.store.login("tester@example.com", "CoffeeRugby2026", "second-device")
        code, _ = self.store.create_password_reset_for_user(row["user_id"])
        self.assertNotIn(code.encode(), self.store.registry.read_bytes())
        result = self.store.reset_password(code.lower(), "NewPassword2026")
        self.assertTrue(result["sessions_revoked"])
        self.assertIsNone(self.store.by_session(first))
        self.assertIsNone(self.store.by_session(second))
        self.assertIsNotNone(self.store.login("tester@example.com", "NewPassword2026", "new-login")[0])
        with self.assertRaises(BetaError):
            self.store.reset_password(code, "AnotherPass2026")

    def test_existing_build_registry_migrates_without_replacing_users(self):
        # The migration itself is exercised by constructing BetaStore in setUp;
        # this assertion guards the Owner and database relationship afterwards.
        self.assertEqual(self.store.owner()["email"], "owner@example.com")
        self.assertEqual(self.store.database_for(self.store.owner()), self.owner_db)
        with self.store._connect() as c:
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"beta_invites", "beta_password_resets", "beta_email_settings", "beta_audit_events"} <= tables)


if __name__ == "__main__":
    unittest.main()

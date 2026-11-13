"""Two-step sign-in, login throttling, and the breach check."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import account_security
from beta_support import BetaError, BetaStore
from sqlite_support import connect


def initialise(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS marker(value TEXT)')


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = BetaStore(self.root, self.root / 'align.sqlite3', initialise)
        self.owner, _code = self.store.ensure_owner('owner@example.com')
        self.password = 'CoffeeRugby2026'
        invite = self.store.create_invite('tester@example.com', 'Tester', initialise, self.owner['user_id'], 'sec-1')[0]
        self.store.complete_invite('tester@example.com', invite['invite_code'], self.password)

    def tearDown(self):
        self.temp.cleanup()

    def test_totp_round_trip_and_second_step(self):
        secret = account_security.generate_secret()
        self.assertTrue(account_security.verify_totp(secret, account_security.totp(secret)))
        self.assertFalse(account_security.verify_totp(secret, '000000'))
        tester = self.store.user_by_email('tester@example.com')
        started = self.store.begin_totp(tester)
        self.assertIn(started['secret'], started['uri'])
        self.store.confirm_totp(tester, account_security.totp(started['secret']))
        pending, token = self.store.login('tester@example.com', self.password, 'device')
        self.assertTrue(pending['totp_required'])
        self.assertIsNone(token)
        row, session = self.store.complete_totp_login(pending['challenge'], account_security.totp(started['secret']))
        self.assertEqual(row['email'], 'tester@example.com')
        self.assertTrue(session)
        self.assertIsNone(self.store.complete_totp_login(pending['challenge'], account_security.totp(started['secret']))[0])

    def test_login_failures_are_rate_limited(self):
        with mock.patch.object(self.store, '_attempt_check'):
            for _ in range(8):
                self.assertIsNone(self.store.login('tester@example.com', 'wrong-password', 'limit')[0])
            with self.assertRaises(BetaError) as caught:
                self.store.login('tester@example.com', 'wrong-password', 'limit')
        self.assertEqual(caught.exception.status, 429)

    def test_breached_password_is_rejected_and_the_range_hides_the_password(self):
        digest = __import__('hashlib').sha1(b'CoffeeRugby2026').hexdigest().upper()

        def hit(prefix):
            self.assertEqual(prefix, digest[:5])
            self.assertNotIn('CoffeeRugby2026', prefix)
            return digest[5:] + ':3'

        with mock.patch.dict(os.environ, {'ALIGN_BREACH_CHECK': '1'}):
            with mock.patch('account_security._hibp_fetch', side_effect=hit):
                with self.assertRaises(BetaError) as caught:
                    self.store.hash_password('CoffeeRugby2026')
        self.assertEqual(caught.exception.code, 'breached_password')
        with mock.patch.dict(os.environ, {'ALIGN_BREACH_CHECK': '0'}):
            self.assertTrue(self.store.hash_password('AnotherPhrase2026'))

    def test_session_cookie_is_first_party(self):
        source = Path('app.py').read_text(encoding='utf-8')
        self.assertIn('SameSite=Lax', source)
        self.assertNotIn('SameSite=None', source)
        self.assertIn("'code': 'totp_required'", source)


if __name__ == '__main__':
    unittest.main()

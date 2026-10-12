import base64
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
import phone_push as push


def subscription():
    public = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    encode = lambda b: base64.urlsafe_b64encode(b).decode().rstrip('=')
    return {'endpoint': 'https://web.push.apple.com/test', 'keys': {'auth': encode(b'a' * 16), 'p256dh': encode(public)}}


class PushTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.c.executescript('CREATE TABLE settings(setting_key TEXT PRIMARY KEY,setting_value TEXT); CREATE TABLE personal_items(id TEXT,kind TEXT,due_at TEXT,done INTEGER); ')
        self.now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
        self.sub = subscription()
        push.subscribe(self.c, self.sub, self.now - timedelta(hours=2))
        self.c.execute("INSERT INTO personal_items VALUES('item','reminder','2026-09-28T12:59',0)")
        self.sent = []

    def tearDown(self):
        self.c.close()

    def send(self, *args):
        self.sent.append(args)

    def test_due_once_and_private(self):
        self.assertEqual(push.dispatch(self.c, self.now, self.send)['sent'], 1)
        self.assertEqual(push.dispatch(self.c, self.now, self.send)['sent'], 0)
        self.assertEqual(len(self.sent), 1)

    def test_london_future_done_and_stale_excluded(self):
        self.c.executemany('INSERT INTO personal_items VALUES(?,?,?,?)', [('future', 'reminder', '2026-09-28T13:01', 0), ('done', 'reminder', '2026-09-28T12:59', 1), ('old', 'reminder', '2026-09-26T12:59', 0)])
        self.assertEqual(push.dispatch(self.c, self.now, self.send)['sent'], 1)

    def test_no_backlog_for_new_device(self):
        self.c.execute('DELETE FROM settings')
        push.subscribe(self.c, self.sub, self.now)
        self.assertEqual(push.dispatch(self.c, self.now, self.send)['sent'], 0)

    def test_failure_retries(self):
        def broken(*args): raise RuntimeError('provider unavailable')
        self.assertEqual(push.dispatch(self.c, self.now, broken)['failed'], 1)
        self.assertEqual(push.dispatch(self.c, self.now, self.send)['sent'], 1)

    def test_expired_device_removed(self):
        def expired(*args):
            error = RuntimeError()
            error.response = SimpleNamespace(status_code=410)
            raise error
        self.assertEqual(push.dispatch(self.c, self.now, expired)['expired'], 1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM settings WHERE setting_key LIKE ?', (push.PREFIX + '%',)).fetchone()[0], 0)

    def test_notification_off(self):
        push.save(self.c, 'notifications', '0')
        self.assertEqual(push.dispatch(self.c, self.now, self.send)['sent'], 0)

    def test_personal_reminders_work_without_legacy_alerts_table(self):
        self.assertFalse(self.c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alerts'"
        ).fetchone())
        self.assertEqual(push.dispatch(self.c, self.now, self.send)['sent'], 1)

    def test_provider_allowlist(self):
        for endpoint in ['http://web.push.apple.com/test', 'https://localhost/test', 'https://web.push.apple.com.evil.test/test', 'https://web.push.apple.com:444/test', 'https://a@web.push.apple.com/test', 'https://127.0.0.1/test']:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                push.validate_subscription({**self.sub, 'endpoint': endpoint})

    def test_bad_key(self):
        with self.assertRaises(ValueError):
            push.validate_subscription({**self.sub, 'keys': {'auth': 'bad', 'p256dh': 'bad'}})

    def test_dispatch_needs_secret_and_post(self):
        class Handler:
            path = '/api/phone-push/dispatch'
            headers = {}
            def send_json(self, status, body): self.status = status
            def clear_request_database(self): pass
        h = Handler()
        with patch.dict('os.environ', {'ALIGN_PUSH_CRON_SECRET': 'test-secret'}):
            push.handle(h, SimpleNamespace(), 'POST')
            self.assertEqual(h.status, 401)
            push.handle(h, SimpleNamespace(), 'GET')
            self.assertEqual(h.status, 405)

    def test_accounts_isolated(self):
        other = sqlite3.connect(':memory:')
        other.execute('CREATE TABLE settings(setting_key TEXT PRIMARY KEY,setting_value TEXT)')
        self.assertIsNone(push.setting(other, push.PREFIX + push.digest(self.sub['endpoint'])))
        other.close()

    def test_real_encryption_without_network(self):
        import requests
        private = ec.generate_private_key(ec.SECP256R1()).private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
        response = requests.Response()
        response.status_code = 201
        with patch.dict('os.environ', {'ALIGN_PUSH_PRIVATE_KEY': base64.urlsafe_b64encode(private).decode()}), patch('requests.Session.send', return_value=response) as send:
            push.send(self.sub, 'align-test', test=True)
        request = send.call_args.args[0]
        self.assertEqual(request.url, self.sub['endpoint'])
        self.assertIn('Authorization', request.headers)
        self.assertNotIn(b'Phone notifications', request.body)
        self.assertFalse(send.call_args.kwargs['allow_redirects'])


import test_owner_builder as fixture


class PushHttpTests(unittest.TestCase):
    setUp = fixture.BuilderTests.setUp
    tearDown = fixture.BuilderTests.tearDown
    request = fixture.BuilderTests.request

    def test_auth_subscription_and_isolation(self):
        token = self.users[0][1]
        other = self.users[1][1]
        self.assertEqual(self.request('GET', '/api/phone-push/status')[0], 401)
        with patch.dict('os.environ', {'ALIGN_PUSH_PRIVATE_KEY': 'test', 'ALIGN_PUSH_PUBLIC_KEY': 'test', 'ALIGN_PUSH_CRON_SECRET': 'test'}):
            sub = subscription()
            self.assertEqual(self.request('POST', '/api/phone-push/subscribe', {'subscription': sub}, token)[0], 200)
            with patch.object(push, 'send') as sender:
                self.assertEqual(self.request('POST', '/api/phone-push/test', {'endpoint': sub['endpoint']}, other)[0], 400)
                sender.assert_not_called()
                self.assertEqual(self.request('POST', '/api/phone-push/test', {'endpoint': sub['endpoint']}, token)[0], 200)
                sender.assert_called_once()
            self.assertEqual(self.request('POST', '/api/phone-push/unsubscribe', {'endpoint': sub['endpoint']}, token)[0], 200)
            self.assertEqual(self.request('POST', '/api/phone-push/test', {'endpoint': sub['endpoint']}, token)[0], 400)


if __name__ == '__main__':
    unittest.main()

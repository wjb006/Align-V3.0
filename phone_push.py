"""Opt-in Web Push. Per-account state uses the existing durable settings table.

The scheduler receives counts only, never planner data or subscriptions.
Delivery is at-least-once; stable notification tags collapse retry duplicates.
"""
import base64
import hashlib
import json
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

PREFIX = 'phone_push_device:'
RECEIPT = 'phone_push_sent:'
LOCK = threading.Lock()
ZONE = ZoneInfo('Europe/London')


def configured():
    return all(os.environ.get(k) for k in ('ALIGN_PUSH_PRIVATE_KEY', 'ALIGN_PUSH_PUBLIC_KEY', 'ALIGN_PUSH_CRON_SECRET'))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def setting(c, key, default=None):
    row = c.execute('SELECT setting_value FROM settings WHERE setting_key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def save(c, key, value):
    c.execute('INSERT INTO settings(setting_key,setting_value) VALUES(?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value', (key, json.dumps(value)))


def validate_subscription(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid phone subscription.')
    endpoint = value.get('endpoint', '')
    if not isinstance(endpoint, str) or len(endpoint) > 2048:
        raise ValueError('Invalid push endpoint.')
    u = urlparse(endpoint)
    # Never turn a user-supplied subscription into arbitrary server-side HTTP.
    allowed = u.hostname in ('web.push.apple.com', 'fcm.googleapis.com', 'updates.push.services.mozilla.com')
    if not allowed or u.scheme != 'https' or u.port not in (None, 443) or u.username or u.password or u.fragment:
        raise ValueError('This browser push provider is not supported. Use Safari, Chrome or Firefox.')
    keys = value.get('keys', {})
    if not isinstance(keys, dict):
        raise ValueError('Invalid push keys.')
    for name, length in (('auth', 16), ('p256dh', 65)):
        v = keys.get(name, '')
        try:
            if not isinstance(v, str) or len(v) > 100:
                raise ValueError()
            raw = base64.b64decode(v + '=' * (-len(v) % 4), altchars=b'-_', validate=True)
            if len(raw) != length:
                raise ValueError()
            if name == 'p256dh':
                from cryptography.hazmat.primitives.asymmetric import ec
                ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
        except (ValueError, TypeError):
            raise ValueError('Invalid push keys.') from None
    return {'endpoint': endpoint, 'keys': {k: keys[k] for k in ('auth', 'p256dh')}}


def subscribe(c, subscription, now=None):
    sub = validate_subscription(subscription)
    key = PREFIX + digest(sub['endpoint'])
    previous = setting(c, key)
    if not previous and c.execute('SELECT COUNT(*) FROM settings WHERE setting_key LIKE ?', (PREFIX + '%',)).fetchone()[0] >= 10:
        raise ValueError('Ten devices are already registered. Disable an unused device first.')
    save(c, key, {'subscription': sub, 'since': previous['since'] if previous else (now or datetime.now(timezone.utc)).isoformat()})
    return key


def send(subscription, tag, test=False):
    from pywebpush import webpush
    import requests
    class NoRedirectSession(requests.Session):
        def request(self, *args, **kwargs):
            kwargs['allow_redirects'] = False
            return super().request(*args, **kwargs)
    with NoRedirectSession() as session:
        response = webpush(subscription_info=validate_subscription(subscription),
            data=json.dumps({'title': 'Align', 'body': 'Phone notifications are connected.' if test else 'You have a reminder. Open Align to see the details.', 'tag': tag}),
            vapid_private_key=os.environ['ALIGN_PUSH_PRIVATE_KEY'],
            vapid_claims={'sub': 'https://beta.getalign.co.uk'},
            ttl=3600, timeout=4, requests_session=session)
        if not 200 <= response.status_code < 300:
            raise ValueError('Push provider did not accept this notification.')


def due_items(c, now):
    """Return due personal reminders without querying retired shift-alert tables."""
    low = (now - timedelta(hours=24)).astimezone(ZONE).replace(tzinfo=None).isoformat(timespec='minutes')
    high = now.astimezone(ZONE).replace(tzinfo=None).isoformat(timespec='minutes')
    rows = [('reminder', r['id'], r['due_at']) for r in c.execute("SELECT id,due_at FROM personal_items WHERE kind='reminder' AND done=0 AND due_at>=? AND due_at<=?", (low, high))]
    for kind, rid, value in rows:
        try:
            at = datetime.fromisoformat(value)
            if at.tzinfo is None:
                at = at.replace(tzinfo=ZONE)
            at = at.astimezone(timezone.utc)
            if now - timedelta(hours=24) <= at <= now:
                yield digest(f'{kind}:{rid}:{value}'), at
        except ValueError:
            continue


def dispatch(c, now=None, sender=send, deadline=None):
    now = now or datetime.now(timezone.utc)
    deadline = deadline or time.monotonic() + 18
    counts = {'sent': 0, 'failed': 0, 'expired': 0}
    if setting(c, 'notifications', 1) in (0, False, '0'):
        return counts
    devices = [(r[0], json.loads(r[1])) for r in c.execute('SELECT setting_key,setting_value FROM settings WHERE setting_key LIKE ?', (PREFIX + '%',))]
    items = list(due_items(c, now))
    # Receipts are needed only for the bounded catch-up window.
    c.execute('DELETE FROM settings WHERE setting_key LIKE ? AND setting_value < ?', (RECEIPT + '%', json.dumps((now - timedelta(days=2)).isoformat())))
    c.commit()
    for key, device in devices:
        since = datetime.fromisoformat(device['since'])
        for event_id, at in items:
            if time.monotonic() >= deadline:
                return counts
            if at < since:
                continue
            receipt = RECEIPT + digest(key + event_id)
            if setting(c, receipt):
                continue
            try:
                sender(device['subscription'], 'align-' + event_id)
            except Exception as exc:
                response = getattr(exc, 'response', None)
                status = getattr(response, 'status_code', None)
                if status in (404, 410):
                    c.execute('DELETE FROM settings WHERE setting_key=?', (key,))
                    c.commit()
                    counts['expired'] += 1
                    break
                counts['failed'] += 1
                # Do not hammer a provider on 429 or transient failure.
                break
            else:
                save(c, receipt, now.isoformat())
                c.commit()
                counts['sent'] += 1
    return counts


def run_scheduler(app):
    if not LOCK.acquire(blocking=False):
        return {'busy': True}
    counts = {'sent': 0, 'failed': 0, 'expired': 0}
    deadline = time.monotonic() + 18
    try:
        store = app.beta_store()
        for item in store.list_users():
            if time.monotonic() >= deadline:
                break
            row = store.user(item['user_id'])
            if not row or not row['active'] or not store.terms_current(row):
                continue
            try:
                with app.FixedDatabaseApp(store.database_for(row)).db_connection() as c:
                    result = dispatch(c, deadline=deadline)
                    save(c, 'phone_push_last_check', datetime.now(timezone.utc).isoformat())
                    for k in counts:
                        counts[k] += result[k]
            except Exception:
                # No email, endpoint, credentials or reminder text in responses/logs.
                counts['failed'] += 1
        return counts
    finally:
        LOCK.release()


def handle(handler, app, method):
    path = urlparse(handler.path).path
    if not path.startswith('/api/phone-push/'):
        return False
    try:
        if path == '/api/phone-push/dispatch':
            token = os.environ.get('ALIGN_PUSH_CRON_SECRET', '')
            if method != 'POST':
                handler.send_json(405, {'error': 'POST required.'})
            elif not token or not secrets.compare_digest(handler.headers.get('Authorization', ''), 'Bearer ' + token):
                handler.send_json(401, {'error': 'Scheduler authentication required.'})
            elif not app.BETA_MODE or not configured():
                handler.send_json(503, {'error': 'Phone notifications are not configured.'})
            else:
                result = run_scheduler(app)
                handler.send_json(503 if result.get('failed') else 200, result)
            return True
        if not app.BETA_MODE:
            handler.send_json(503, {'error': 'Use hosted Align for phone notifications.'})
            return True
        if not handler.require_beta_user():
            return True
        if method != 'GET' and not handler.beta_same_origin():
            return True
        body = handler.read_json() if method == 'POST' else {}
        with app.db_connection() as c:
            if path == '/api/phone-push/status' and method == 'GET':
                result = {'configured': configured(), 'public_key': os.environ.get('ALIGN_PUSH_PUBLIC_KEY', ''), 'last_check': setting(c, 'phone_push_last_check')}
            elif path == '/api/phone-push/subscribe' and method == 'POST':
                if not configured():
                    raise ValueError('The server notification setup is not finished yet.')
                subscribe(c, body.get('subscription'))
                result = {'saved': True}
            elif path in ('/api/phone-push/unsubscribe', '/api/phone-push/test') and method == 'POST':
                endpoint = body.get('endpoint', '')
                if not isinstance(endpoint, str) or len(endpoint) > 2048:
                    raise ValueError('Invalid device.')
                key = PREFIX + digest(endpoint)
                device = setting(c, key)
                if path.endswith('/unsubscribe'):
                    c.execute('DELETE FROM settings WHERE setting_key=?', (key,))
                    result = {'saved': True}
                else:
                    if not device:
                        raise ValueError('Enable notifications on this device first.')
                    now = datetime.now(timezone.utc)
                    previous = setting(c, 'phone_push_test_at')
                    if previous and (now - datetime.fromisoformat(previous)).total_seconds() < 30:
                        raise ValueError('Wait 30 seconds before another test.')
                    save(c, 'phone_push_test_at', now.isoformat())
                    c.commit()
                    try:
                        send(device['subscription'], 'align-test', test=True)
                    except Exception:
                        handler.send_json(503, {'error': 'The push provider did not accept the test. Try enabling notifications again.'})
                        return True
                    result = {'accepted': True}
            else:
                handler.send_json(404, {'error': 'Not found.'})
                return True
        handler.send_json(200, result)
    except (ValueError, TypeError, KeyError):
        handler.send_json(400, {'error': 'Check the notification settings and try again.'})
    except Exception:
        handler.send_json(503, {'error': 'Phone notification service is temporarily unavailable.'})
    finally:
        handler.clear_request_database()
    return True

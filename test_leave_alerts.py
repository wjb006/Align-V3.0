"""Leave-now alerts stay opted out until the account asks, and follow live delay and weather."""
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

import phone_push
from leave_alerts import alert_time, due, save_settings


def connection():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE settings(setting_key TEXT PRIMARY KEY, setting_value TEXT);
        CREATE TABLE organiser_events(
            id INTEGER PRIMARY KEY, title TEXT, start_at TEXT, notes TEXT, all_day INTEGER, location TEXT
        );
    ''')
    return db


def event(notes, title='Clinic', location='12 Private Road CH41 6AZ'):
    return {
        'id': 7, 'title': title, 'all_day': 0,
        'start_at': '2026-09-28T13:30',
        'notes': notes, 'location': location,
    }


NOTES = '''Allowance: 5 minutes before leaving
[Align travel steps]
[{"mode":"walk","start":"2026-09-28T11:40:00+00:00","from":"Home","to":"Near"},{"mode":"bus","service":"418","from":"Near","to":"Hospital","start":"2026-09-28T11:50:00+00:00"}]
[/Align travel steps]'''


class LeaveAlertTests(unittest.TestCase):
    def test_opt_in_is_required_and_address_is_omitted(self):
        now = datetime(2026, 9, 28, 11, 36, tzinfo=timezone.utc)
        self.assertEqual(due(connection(), now, {'enabled': False, 'window_minutes': 8}), [])
        row = event(NOTES)
        when, body, delay, weather = alert_time(row, now)
        self.assertEqual(delay, 0)
        self.assertEqual(weather, 0)
        self.assertEqual(when, datetime(2026, 9, 28, 11, 35, tzinfo=timezone.utc))
        self.assertIn('Clinic', body)
        self.assertNotIn('CH41', body)
        self.assertNotIn('Private Road', body)

    def test_delay_moves_the_alert_later_and_weather_moves_it_earlier(self):
        now = datetime(2026, 9, 28, 11, 36, tzinfo=timezone.utc)
        def late(_legs):
            return {'legs': [{'service': '418', 'delay_minutes': 6}]}
        when, body, delay, _weather = alert_time(event(NOTES), now, delay_lookup=late)
        self.assertEqual(delay, 6)
        self.assertEqual(when, datetime(2026, 9, 28, 11, 41, tzinfo=timezone.utc))
        self.assertIn('6 minutes later', body)
        earlier, weather_body, _delay, weather = alert_time(event(NOTES), now, weather_lookup=lambda _start: 10)
        self.assertEqual(weather, 10)
        self.assertEqual(earlier, datetime(2026, 9, 28, 11, 25, tzinfo=timezone.utc))
        self.assertIn('Weather adds 10 minutes', weather_body)

    def test_dispatch_sends_one_leave_alert_for_the_signed_in_account(self):
        db = connection()
        phone_push.save(db, 'leave_alerts', save_settings({'enabled': True, 'window_minutes': 8}))
        db.execute('INSERT INTO organiser_events(title,start_at,notes,all_day,location) VALUES(?,?,?,0,?)',
                   ('Clinic', '2026-09-28T13:30', NOTES, '12 Private Road CH41 6AZ'))
        db.execute('CREATE TABLE personal_items(id TEXT,kind TEXT,due_at TEXT,done INTEGER)')
        now = datetime(2026, 9, 28, 11, 36, tzinfo=timezone.utc)
        sub = __import__('test_phone_push').subscription()
        phone_push.subscribe(db, sub, now - timedelta(hours=2))
        sent = []
        self.assertEqual(phone_push.dispatch(db, now, lambda *args: sent.append(args))['sent'], 1)
        self.assertIn('Time to leave for Clinic.', sent[0][3])
        self.assertNotIn('CH41', sent[0][3])
        self.assertEqual(phone_push.dispatch(db, now, lambda *args: sent.append(args))['sent'], 0)
        other = sqlite3.connect(':memory:')
        other.row_factory = sqlite3.Row
        other.execute('CREATE TABLE settings(setting_key TEXT PRIMARY KEY, setting_value TEXT)')
        self.assertIsNone(phone_push.setting(other, 'leave_alerts'))
        other.close()

    def test_missing_journey_does_not_invent_a_time(self):
        now = datetime(2026, 9, 28, 11, 36, tzinfo=timezone.utc)
        self.assertIsNone(alert_time(event('Meet at the usual place'), now))

    def test_settings_reject_a_wide_window(self):
        with self.assertRaises(ValueError):
            save_settings({'enabled': True, 'window_minutes': 90})
        self.assertEqual(save_settings({'enabled': 1, 'window_minutes': '8'}), {'enabled': True, 'window_minutes': 8})
        self.assertTrue(json.dumps(save_settings({'enabled': True})))


if __name__ == '__main__':
    unittest.main()

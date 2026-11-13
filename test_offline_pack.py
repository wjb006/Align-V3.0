"""The offline pack is the next few days already stored for this account."""
import sqlite3
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from offline_pack import pack


class OfflinePackTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE settings(setting_key TEXT PRIMARY KEY, setting_value TEXT);
            CREATE TABLE organiser_events(
                id INTEGER PRIMARY KEY, title TEXT, start_at TEXT, end_at TEXT,
                all_day INTEGER, location TEXT, notes TEXT
            );
            CREATE TABLE shifts(
                id INTEGER PRIMARY KEY, work_date TEXT, start_time TEXT, end_time TEXT,
                location_name TEXT, shift_type_name TEXT
            );
        ''')
        self.now = datetime(2026, 11, 13, 19, 0, tzinfo=ZoneInfo('Europe/London'))

    def test_pack_keeps_four_days_of_plan_travel_and_cached_weather_only(self):
        self.db.execute(
            'INSERT INTO organiser_events VALUES(1,?,?,?,?,?,?)',
            ('Clinic', '2026-11-13T09:00', '2026-11-13T12:00', 0, 'Hospital',
             'Private note\n[Align travel]\nBus 418\n[/Align travel]'),
        )
        self.db.execute(
            'INSERT INTO organiser_events VALUES(2,?,?,?,?,?,?)',
            ('Later', '2026-11-20T09:00', '2026-11-20T10:00', 0, 'Away', ''),
        )
        self.db.execute(
            "INSERT INTO shifts VALUES(4,'2026-11-14','08:00','16:00','Main Hospital','Wards')"
        )
        self.db.execute(
            "INSERT INTO settings VALUES('weather_forecast_v1', ?)",
            ('{"checked_at":"2026-11-13T18:00+00:00","data":{"source":"Open-Meteo","daily":{"time":["2026-11-13"],"temperature_2m_max":[12],"temperature_2m_min":[6],"weather_code":[1],"precipitation_probability_max":[20]}}}',),
        )
        with patch('urllib.request.urlopen', side_effect=AssertionError('offline pack called the network')):
            result = pack(self.db, self.now)
        self.assertEqual(result['from'], '2026-11-13')
        self.assertEqual(result['until'], '2026-11-16')
        self.assertEqual([item['title'] for item in result['events']], ['Clinic'])
        self.assertIn('Bus 418', result['events'][0]['travel'])
        self.assertNotIn('Private note', result['events'][0]['travel'])
        self.assertEqual(result['shifts'][0]['shift_type_name'], 'Wards')
        self.assertTrue(result['weather']['cached'])
        self.assertEqual(result['weather']['daily']['temperature_2m_max'], [12])
        worker = Path('static/service-worker.js').read_text(encoding='utf-8')
        self.assertIn("url.pathname === '/api/personal/offline-pack'", worker)
        app = Path('static/app.js').read_text(encoding='utf-8')
        self.assertIn('/api/personal/offline-pack', app)
        self.assertIn("addEventListener('online'", app)
        self.assertIn("addEventListener('offline'", app)


if __name__ == '__main__':
    unittest.main()

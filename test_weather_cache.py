import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
import weather_cache as w


class WeatherCacheTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.execute('CREATE TABLE settings(setting_key TEXT PRIMARY KEY,setting_value TEXT)')
        self.now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
        self.place = {'latitude': 53.39, 'longitude': -3.01}
        self.forecast = {'current': {'temperature_2m': 14}, 'daily': {}, 'hourly': {}}
    def tearDown(self): self.c.close()

    def test_cache_survives_repeated_calls(self):
        primary = Mock(return_value=dict(self.forecast))
        a = w.cached_forecast(self.c, self.place, primary, self.now)
        b = w.cached_forecast(self.c, self.place, primary, self.now + timedelta(minutes=5))
        self.assertEqual(primary.call_count, 1)
        self.assertEqual(a['checked_at'], b['checked_at'])

    def test_backup_and_cooldown(self):
        primary = Mock(side_effect=ValueError('rate limited'))
        backup = {**self.forecast, 'source': 'MET Norway'}
        with patch.object(w, 'met_forecast', return_value=(backup, (self.now + timedelta(minutes=30)).isoformat(), '')) as met:
            result = w.cached_forecast(self.c, self.place, primary, self.now)
            self.assertEqual(result['source'], 'MET Norway')
            w.cached_forecast(self.c, self.place, primary, self.now + timedelta(minutes=31))
            self.assertEqual(primary.call_count, 1)
            self.assertEqual(met.call_count, 2)

    def test_failed_refresh_preserves_saved_timestamp(self):
        first = w.cached_forecast(self.c, self.place, Mock(return_value=dict(self.forecast)), self.now)
        with patch.object(w, 'met_forecast', side_effect=ValueError('offline')):
            result = w.cached_forecast(self.c, self.place, Mock(side_effect=ValueError('offline')), self.now + timedelta(hours=1))
        self.assertTrue(result['stale'])
        self.assertEqual(first['checked_at'], result['checked_at'])
        provider = Mock()
        w.cached_forecast(self.c, self.place, provider, self.now + timedelta(hours=1, minutes=1))
        provider.assert_not_called()

    def test_other_location_never_gets_previous_forecast(self):
        w.cached_forecast(self.c, self.place, Mock(return_value=dict(self.forecast)), self.now)
        with patch.object(w, 'met_forecast', side_effect=ValueError('offline')), self.assertRaises(ValueError):
            w.cached_forecast(self.c, {'latitude': 1, 'longitude': 2}, Mock(side_effect=ValueError('offline')), self.now)

    def test_normalises_timezone_missing_probability_and_units(self):
        data = {'properties': {'timeseries': [{'time': '2026-09-28T12:00:00Z', 'data': {'instant': {'details': {'air_temperature': 15, 'wind_speed': 5}}, 'next_1_hours': {'summary': {'symbol_code': 'rain'}, 'details': {}}}}]}}
        result = w.normalise_met(data, self.now)
        self.assertEqual(result['hourly']['time'][0], '2026-09-28T13:00')
        self.assertEqual(result['hourly']['wind_speed_10m'][0], 18)
        self.assertIsNone(result['hourly']['precipitation_probability'][0])
        self.assertEqual(result['daily']['weather_code'][0], 61)


if __name__ == '__main__': unittest.main()

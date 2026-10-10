"""Fresh setup integration tests; all databases are temporary."""
import copy
import gc
import tempfile
import threading
import unittest
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

import app
from test_calendar_sync import CalendarSyncTests, QuietHandler


class WorkSetupTests(unittest.TestCase):
    request = CalendarSyncTests.request
    json_request = CalendarSyncTests.json_request

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='align-setup-test-')
        self.original_database = app.DATABASE
        app.DATABASE = Path(self.temp.name) / 'test.sqlite3'
        app.initialise_database()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        app.DATABASE = self.original_database
        gc.collect()
        self.temp.cleanup()

    def configuration(self):
        data = self.json_request('GET', '/api/work-setup')
        data.update(contracted_hours=20, duration_minutes=240,
            slots=[{'key': 'early', 'start_time': '07:30', 'duration_minutes': 240},
                   {'key': 'morning', 'start_time': '08:30', 'duration_minutes': 240},
                   {'key': 'afternoon', 'start_time': '13:00', 'duration_minutes': 240}],
            areas=[{'key': 'wards', 'name': 'Wards', 'slots': ['early']},
                   {'key': 'clinic', 'name': 'Clinic', 'slots': ['morning', 'afternoon']}],
            locations=[{'key': 'arrowe', 'name': 'Arrowe Park', 'address': 'Arrowe Park Road', 'colour': '#23AA88'},
                       {'key': 'clatterbridge', 'name': 'Clatterbridge', 'address': 'Clatterbridge Road', 'colour': '#AA3388'}],
            assignments=[{'location_key': 'arrowe', 'area_key': 'wards', 'slot_key': 'early', 'days': list(app.WEEK_DAYS)},
                         {'location_key': 'arrowe', 'area_key': 'clinic', 'slot_key': 'morning', 'days': list(app.WEEKDAY_DAYS)},
                         {'location_key': 'arrowe', 'area_key': 'clinic', 'slot_key': 'afternoon', 'days': list(app.WEEKDAY_DAYS)},
                         {'location_key': 'clatterbridge', 'area_key': 'clinic', 'slot_key': 'afternoon', 'days': list(app.WEEKDAY_DAYS)}])
        return data

    def test_starts_empty_then_saves_reusable_rules(self):
        fresh = self.json_request('GET', '/api/bootstrap')
        self.assertEqual(fresh['settings']['user_name'], '')
        self.assertFalse(fresh['settings']['onboarding_completed'])
        for group in ('locations', 'shift_types', 'templates'):
            self.assertEqual(fresh['master'][group], [])
        saved = self.json_request('PUT', '/api/work-setup', self.configuration())
        self.assertEqual(saved, {'patterns': 4, 'retired': 0})
        result = self.json_request('GET', '/api/bootstrap')
        self.assertEqual(result['settings']['contracted_hours'], 20)
        self.assertEqual(result['settings']['work_setup_completed'], '1')
        templates = result['master']['templates']
        self.assertEqual({t['sub_shift_type'] for t in templates}, {'AM', 'PM'})
        self.assertEqual({t['colour'] for t in templates}, {'#23AA88', '#AA3388'})
        weekend = [t for t in templates if 'Saturday' in t['applicable_days']]
        self.assertEqual([(t['shift_type_name'], t['start_time'], t['end_time']) for t in weekend], [('Wards', '07:30', '11:30')])
        ids = {t['id'] for t in templates}
        reloaded = self.json_request('GET', '/api/work-setup')
        self.json_request('PUT', '/api/work-setup', reloaded)
        self.assertEqual(ids, {t['id'] for t in self.json_request('GET', '/api/bootstrap')['master']['templates']})
        self.assertEqual(self.json_request('GET', '/api/shifts'), [])

    def test_invalid_day_rolls_back_every_change(self):
        before = self.json_request('GET', '/api/work-setup')
        payload = self.configuration()
        payload['assignments'][0]['days'] = []
        self.json_request('PUT', '/api/work-setup', payload, expected=400)
        self.assertEqual(self.json_request('GET', '/api/work-setup'), before)

    def test_validation_and_stale_tab(self):
        original = self.configuration()
        for field, value in [('contracted_hours', -2), ('contracted_hours', float('nan')), ('duration_minutes', 1440)]:
            payload = copy.deepcopy(original)
            payload[field] = value
            self.json_request('PUT', '/api/work-setup', payload, expected=400)
        payload = copy.deepcopy(original)
        payload['locations'][0]['colour'] = 'not-a-colour'
        self.json_request('PUT', '/api/work-setup', payload, expected=400)
        self.json_request('PUT', '/api/work-setup', original)
        response = self.json_request('PUT', '/api/work-setup', original, expected=400)
        self.assertIn('another tab', response['error'])

    def test_days_half_day_rules_and_saved_shifts_unchanged(self):
        self.json_request('PUT', '/api/work-setup', self.configuration())
        boot = self.json_request('GET', '/api/bootstrap')
        templates = boot['master']['templates']
        wards = next(t for t in templates if t['shift_type_name'] == 'Wards')
        clinic_am = next(t for t in templates if t['shift_type_name'] == 'Clinic' and t['start_time'] == '08:30')
        clinic_pm = next(t for t in templates if t['shift_type_name'] == 'Clinic' and t['location_name'] == 'Arrowe Park' and t['start_time'] == '13:00')
        monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 + 7)
        def add(template, day=monday, **extras):
            return {'shifts': [{'work_date': day.isoformat(), 'template_id': template['id'], **extras}]}
        self.json_request('POST', '/api/shifts', add(wards))
        self.json_request('POST', '/api/shifts', add(clinic_am), expected=400)
        # Non-overlapping AM choices are also excluded: only one AM and one PM.
        self.json_request('POST', '/api/shifts', add(clinic_am, start_time='11:30', end_time='12:30'), expected=400)
        self.json_request('POST', '/api/shifts', add(clinic_pm))
        self.json_request('POST', '/api/shifts', add(clinic_am, monday + timedelta(days=5)), expected=400)
        saved_shifts = self.json_request('GET', '/api/shifts')
        payload = self.json_request('GET', '/api/work-setup')
        payload['locations'][0]['colour'] = '#112233'
        for assignment in payload['assignments']:
            assignment['days'] = ['Monday']
        # Remove just the AM clinic choice, keeping both areas and locations assigned.
        payload['assignments'] = [a for a in payload['assignments'] if not a['slot_key'].startswith('08:30')]
        response = self.json_request('PUT', '/api/work-setup', payload)
        self.assertEqual(response['retired'], 1)
        # Colour metadata is intentionally live; the stored shift snapshot is not rewritten.
        without_display_colours = lambda rows: [{k:v for k,v in row.items() if k not in ('location_colour','shift_type_colour')} for row in rows]
        self.assertEqual(without_display_colours(self.json_request('GET', '/api/shifts')), without_display_colours(saved_shifts))
        self.assertEqual(len(self.json_request('GET', '/api/bootstrap')['master']['templates']), 3)

    def test_overnight_slot_and_duplicate_assignment(self):
        payload = self.configuration()
        payload['slots'][2].update(start_time='22:00', duration_minutes=480, break_minutes=30)
        self.json_request('PUT', '/api/work-setup', payload)
        templates = self.json_request('GET', '/api/bootstrap')['master']['templates']
        overnight = [t for t in templates if t['start_time'] == '22:00']
        self.assertTrue(all(t['end_time'] == '06:00' and t['sub_shift_type'] == 'PM' for t in overnight))
        payload = self.json_request('GET', '/api/work-setup')
        payload['assignments'].append(payload['assignments'][0])
        self.json_request('PUT', '/api/work-setup', payload, expected=400)


if __name__ == '__main__':
    unittest.main()

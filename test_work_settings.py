"""View-first library edits: isolated databases, no real user data."""
import copy
from datetime import date, timedelta
import unittest

import app
from test_work_setup import WorkSetupTests


class WorkSettingsTests(unittest.TestCase):
    setUp = WorkSetupTests.setUp
    tearDown = WorkSetupTests.tearDown
    request = WorkSetupTests.request
    json_request = WorkSetupTests.json_request
    configuration = WorkSetupTests.configuration

    def load(self):
        value = self.json_request('GET', '/api/work-setup')
        value['save_mode'] = 'settings'
        return value

    def save(self, value, status=200):
        return self.json_request('PUT', '/api/work-setup', value, expected=status)

    def test_first_items_can_be_added_in_any_order(self):
        value = self.load()
        value['areas'] = [{'key': 'area', 'name': 'Wards', 'colour': '#112233', 'slots': []}]
        self.assertEqual(self.save(value)['patterns'], 0)
        value = self.load()
        value['locations'] = [{'key': 'place', 'name': 'Hospital', 'address': 'Test address', 'colour': '#445566'}]
        self.assertEqual(self.save(value)['patterns'], 0)
        value = self.load()
        value['slots'] = [{'key': 'time', 'start_time': '07:30', 'duration_minutes': 240, 'break_minutes': 0}]
        value['areas'][0]['slots'] = ['time']
        value['assignments'] = [{'location_key': value['locations'][0]['key'], 'area_key': value['areas'][0]['key'], 'slot_key': 'time', 'days': ['Saturday', 'Sunday']}]
        self.assertEqual(self.save(value)['patterns'], 1)
        boot = self.json_request('GET', '/api/bootstrap')
        self.assertEqual(boot['settings']['work_setup_completed'], '1')
        self.assertEqual(boot['master']['templates'][0]['applicable_days'], ['Saturday', 'Sunday'])
        self.assertEqual(self.json_request('GET', '/api/shifts'), [])

    def test_new_area_links_preserve_existing_rules(self):
        self.save(self.configuration())
        before = self.load()
        value = copy.deepcopy(before)
        slot_key = value['slots'][0]['key']
        value['areas'].append({'key': 'new-area', 'name': 'Day Unit', 'colour': '#AA3388', 'slots': [slot_key]})
        value['assignments'].append({'location_key': value['locations'][0]['key'], 'area_key': 'new-area', 'slot_key': slot_key, 'days': ['Tuesday', 'Thursday']})
        self.assertEqual(self.save(value)['patterns'], 5)
        after = self.load()
        for assignment in before['assignments']:
            self.assertIn(assignment, after['assignments'])
        bad = self.load()
        bad['areas'][0]['name'] = 'Must roll back'
        bad['assignments'][0]['days'] = []
        self.save(bad, 400)
        self.assertEqual(self.load(), after)

    def test_edit_time_keeps_existing_bookings_and_other_times(self):
        self.save(self.configuration())
        boot = self.json_request('GET', '/api/bootstrap')
        template = next(t for t in boot['master']['templates'] if t['shift_type_name'] == 'Wards')
        day = date.today() + timedelta(days=14-date.today().weekday())
        self.json_request('POST', '/api/shifts', {'shifts': [{'work_date': day.isoformat(), 'template_id': template['id']}]})
        old_shifts = self.json_request('GET', '/api/shifts')
        old = self.load()
        value = copy.deepcopy(old)
        value['slots'][0]['start_time'] = '07:45'
        self.save(value)
        after = self.load()
        self.assertEqual([s['start_time'] for s in after['slots']], ['07:45', '08:30', '13:00'])
        self.assertEqual(self.json_request('GET', '/api/shifts'), old_shifts)
        # A stale edit must never overwrite a newly saved setting.
        self.assertIn('another tab', self.save(old, 400)['error'])

    def test_view_is_read_only_and_menu_migration_is_once_only(self):
        before = self.load()
        self.assertEqual(self.load(), before)
        boot = self.json_request('GET', '/api/bootstrap')
        branches = boot['master']['branches']
        self.assertEqual(next(b['title'] for b in branches if b['branch_key'] == 'work'), 'Work Settings')
        self.assertFalse(any(b['branch_key'] == 'locations' for b in branches))
        with app.db_connection() as connection:
            connection.execute("UPDATE menu_branches SET active=1 WHERE branch_key='locations'")
            connection.execute("UPDATE menu_branches SET title='My custom work menu' WHERE branch_key='work'")
        app.initialise_database()
        with app.db_connection() as connection:
            self.assertEqual(connection.execute("SELECT active FROM menu_branches WHERE branch_key='locations'").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT title FROM menu_branches WHERE branch_key='work'").fetchone()[0], 'My custom work menu')


if __name__ == '__main__':
    unittest.main()

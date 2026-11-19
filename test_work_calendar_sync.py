"""Shift assignment to the Work calendar and a mocked iCloud push.

These tests never contact Apple and never use a real app-specific password.
"""
import logging
import unittest
from datetime import date, timedelta

import app
import work_calendar
from icloud_sync import CloudError, ICloudSync
from test_icloud import FakeApple
from test_support import IsolatedAppServer


class CalendarNameTests(unittest.TestCase):
    def test_work_names_match_across_emoji_spelling_and_invisible_marks(self):
        self.assertEqual(work_calendar.calendar_label('🩸Work'), 'work')
        self.assertEqual(work_calendar.calendar_label('🩸\uFE0FWork Calendar'), 'work calendar')
        self.assertEqual(work_calendar.calendar_label('Work Calender'), 'work calendar')
        self.assertEqual(work_calendar.calendar_label('  work-calendar  '), 'work calendar')
        self.assertTrue(work_calendar.is_work_calendar_name('🩸\uFE0FWork'))
        self.assertFalse(work_calendar.is_work_calendar_name('📆 Calendar'))
        self.assertFalse(work_calendar.is_work_calendar_name('Workshops'))
        self.assertFalse(work_calendar.is_work_calendar_name('My work diary'))


class ResumeFailureTests(unittest.TestCase):
    def test_resume_error_is_visible_and_omits_the_password(self):
        from unittest.mock import MagicMock, patch

        store = MagicMock()
        store.load_icloud.return_value = ('person@example.invalid', 'secret-value')
        store.database_for.return_value = 'align.sqlite3'

        class Boom:
            def __init__(self, app_module):
                self.client = None
                self.last_error = None
                self.message = ''
                self.reconnect_required = False
                self.last_sync = None
                self.enabled = False
                self.options = []

            def resume(self, username, password):
                raise CloudError('Check the Apple Account email and app-specific password.')

        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Capture()
        logger = logging.getLogger('align.icloud')
        logger.addHandler(handler)
        try:
            with patch.object(app, 'beta_store', return_value=store), patch.dict(app.BETA_ICLOUD_MANAGERS, {}, clear=True), patch('icloud_sync.ICloudSync', Boom):
                manager = app.beta_icloud_manager({'user_id': 'owner'})
        finally:
            logger.removeHandler(handler)
        self.assertTrue(manager.reconnect_required)
        self.assertIn('app-specific password', manager.message)
        self.assertNotIn('secret-value', manager.message)
        self.assertNotIn('secret-value', '\n'.join(records))
        public = app.public_icloud_data(manager)
        self.assertTrue(public['reconnect_required'])
        self.assertEqual(public['last_error'], manager.last_error)
        self.assertNotIn('secret-value', str(public))


class ShiftCalendarTests(unittest.TestCase):
    setUp = IsolatedAppServer.setUp
    tearDown = IsolatedAppServer.tearDown
    request = IsolatedAppServer.request
    json_request = IsolatedAppServer.json_request

    def test_saved_shift_is_listed_on_the_matching_work_calendar_only(self):
        location = self.json_request('POST', '/api/locations', {'name': 'Test Ward', 'address': '1 Test Road'})
        area = self.json_request('POST', '/api/shift-types', {'name': 'Clinic'})
        day = (date.today() + timedelta(days=10)).isoformat()
        with app.db_connection() as connection:
            work_id = connection.execute(
                "INSERT INTO organiser_sections(name,active) VALUES(?,1)", ('Work Calendar',)
            ).lastrowid
            other_id = connection.execute(
                "INSERT INTO organiser_sections(name,active) VALUES(?,1)", ('Appointments',)
            ).lastrowid
            connection.execute(
                """INSERT INTO calendar_links(target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled)
                   VALUES('organiser_section',?,?,?,1,1)""",
                (str(work_id), 'https://caldav.icloud.com/test/work/', '🩸\uFE0FWork Calender'),
            )
            connection.execute(
                """INSERT INTO calendar_links(target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled)
                   VALUES('organiser_section',?,?,?,1,1)""",
                (str(other_id), 'https://caldav.icloud.com/test/other/', '📆 Calendar'),
            )
            connection.commit()
        created = self.json_request('POST', '/api/shifts', {
            'work_date': day, 'location_id': location['id'], 'shift_type_id': area['id'],
            'start_time': '08:30', 'end_time': '12:30', 'break_minutes': 0, 'notes': 'Handover',
        })
        self.assertTrue(created['calendar']['linked'])
        self.assertIn('Work', created['calendar']['name'])
        self.assertEqual(created['calendar']['shift_count'], 1)
        work = self.json_request('GET', f'/api/sections/{work_id}', expected=200)
        shifts = [event for event in work['events'] if event['source_kind'] == 'shift']
        self.assertEqual(len(shifts), 1)
        self.assertEqual(shifts[0]['title'], 'Test Ward – Clinic')
        self.assertTrue(shifts[0]['start_at'].startswith(day + 'T08:30'))
        other = self.json_request('GET', f'/api/sections/{other_id}', expected=200)
        self.assertFalse(any(event['source_kind'] == 'shift' for event in other['events']))
        with app.db_connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM organiser_events').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM shifts').fetchone()[0], 1)
            listed = work_calendar.shift_records(connection)
        self.assertEqual(listed[0]['id'], created['shifts'][0]['id'])
        sections = self.json_request('GET', '/api/sections', expected=200)
        work_row = next(item for item in sections if item['id'] == work_id)
        self.assertEqual(work_row['shift_count'], 1)
        self.assertEqual(next(item for item in sections if item['id'] == other_id)['shift_count'], 0)

    def test_shift_without_a_work_calendar_stays_in_align(self):
        location = self.json_request('POST', '/api/locations', {'name': 'Test Ward', 'address': '1 Test Road'})
        area = self.json_request('POST', '/api/shift-types', {'name': 'Clinic'})
        day = (date.today() + timedelta(days=11)).isoformat()
        created = self.json_request('POST', '/api/shifts', {
            'work_date': day, 'location_id': location['id'], 'shift_type_id': area['id'],
            'start_time': '13:00', 'end_time': '17:00', 'break_minutes': 0,
        })
        self.assertFalse(created['calendar']['linked'])
        self.assertIn('saved in Align', created['calendar']['message'])
        with app.db_connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM shifts').fetchone()[0], 1)


class ShiftICloudPushTests(unittest.TestCase):
    setUpBase = IsolatedAppServer.setUp
    tearDown = IsolatedAppServer.tearDown
    request = IsolatedAppServer.request
    json_request = IsolatedAppServer.json_request

    def setUp(self):
        self.setUpBase()
        self.syncer = ICloudSync(app, FakeApple)
        self.syncer.discover('test@example.invalid', 'fake-test-password')
        self.fake = self.syncer.client
        self.personal = 'https://caldav.icloud.com/test/personal/'
        self.work = 'https://caldav.icloud.com/test/work/'
        self.fake.calendars = {self.personal: None, self.work: None}
        with app.db_connection() as connection:
            connection.execute(
                'UPDATE icloud_config SET account_hash=?,target_url=?,read_urls=? WHERE id=1',
                (self.syncer.account, self.personal, '["' + self.personal + '","' + self.work + '"]'),
            )
            personal_id = connection.execute("INSERT INTO organiser_sections(name,active) VALUES('Appointments',1)").lastrowid
            work_id = connection.execute("INSERT INTO organiser_sections(name,active) VALUES('Work Calendar',1)").lastrowid
            connection.execute(
                """INSERT INTO calendar_links(target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled)
                   VALUES('organiser_section',?,?, '📆 Calendar',1,1)""",
                (str(personal_id), self.personal),
            )
            connection.execute(
                """INSERT INTO calendar_links(target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled)
                   VALUES('organiser_section',?,?, '🩸Work',1,1)""",
                (str(work_id), self.work),
            )
            connection.commit()
            self.work_id = work_id
        self.syncer.enabled = True
        location = self.json_request('POST', '/api/locations', {'name': 'Test Ward', 'address': '1 Test Road'})
        area = self.json_request('POST', '/api/shift-types', {'name': 'Clinic'})
        self.day = (date.today() + timedelta(days=12)).isoformat()
        created = self.json_request('POST', '/api/shifts', {
            'work_date': self.day, 'location_id': location['id'], 'shift_type_id': area['id'],
            'start_time': '08:00', 'end_time': '16:00', 'break_minutes': 0, 'notes': 'Handover',
        })
        self.shift_id = created['shifts'][0]['id']

    def shift_urls(self):
        return [url for method, url in self.fake.calls if method == 'PUT' and f'shift-{self.shift_id}' in url]

    def test_shift_is_pushed_only_to_the_work_calendar_and_replaces_cloud_edits(self):
        self.syncer.sync()
        pushed = self.shift_urls()
        self.assertEqual(len(pushed), 1)
        self.assertTrue(pushed[0].startswith(self.work))
        self.assertFalse(any(url.startswith(self.personal) and f'shift-{self.shift_id}' in url for _, url in self.fake.calls))
        body = self.fake.objects[pushed[0]][0]
        self.assertIn(b'Test Ward', body)
        self.assertIn(b'Clinic', body)
        self.assertIn('Pushed 1 shift to', self.syncer.message)
        self.assertIn('Work', self.syncer.message)
        self.assertIsNone(self.syncer.last_error)
        edited = body.replace(b'SUMMARY:', b'SUMMARY:Changed in iCloud ')
        self.fake.objects[pushed[0]] = (edited, '"external"')
        self.syncer.sync()
        replaced = self.fake.objects[pushed[0]][0]
        self.assertIn(b'Test Ward', replaced)
        self.assertNotIn(b'Changed in iCloud', replaced)
        self.json_request('DELETE', f'/api/shifts/{self.shift_id}', expected=200)
        self.syncer.sync()
        self.assertNotIn(pushed[0], self.fake.objects)
        self.assertTrue(any(method == 'DELETE' and url == pushed[0] for method, url in self.fake.calls))

    def test_sync_failure_is_logged_without_the_app_password(self):
        self.fake.events = lambda *args: (_ for _ in ()).throw(CloudError('Calendar is temporarily unavailable.'))
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Capture()
        logger = logging.getLogger('align.icloud')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            self.syncer.sync()
        finally:
            logger.removeHandler(handler)
        self.assertEqual(self.syncer.last_error, 'Calendar is temporarily unavailable.')
        self.assertTrue(records)
        joined = '\n'.join(records)
        self.assertIn('Calendar is temporarily unavailable.', joined)
        self.assertNotIn('fake-test-password', joined)
        self.assertNotIn('test@example.invalid', joined)
        status = self.syncer.status()
        self.assertEqual(status['last_error'], self.syncer.last_error)
        public = app.public_icloud_data(self.syncer)
        self.assertEqual(public['last_error'], self.syncer.last_error)
        self.assertNotIn('fake-test-password', str(public))


class UnlinkedShiftSyncTests(unittest.TestCase):
    setUpBase = IsolatedAppServer.setUp
    tearDown = IsolatedAppServer.tearDown
    request = IsolatedAppServer.request
    json_request = IsolatedAppServer.json_request

    def test_sync_does_not_push_a_shift_when_no_work_calendar_is_linked(self):
        self.setUpBase()
        syncer = ICloudSync(app, FakeApple)
        syncer.discover('test@example.invalid', 'fake-test-password')
        url = next(iter(syncer.client.calendars))
        with app.db_connection() as connection:
            connection.execute(
                'UPDATE icloud_config SET account_hash=?,target_url=?,read_urls=? WHERE id=1',
                (syncer.account, url, '["' + url + '"]'),
            )
            section_id = connection.execute("INSERT INTO organiser_sections(name,active) VALUES('Appointments',1)").lastrowid
            connection.execute(
                """INSERT INTO calendar_links(target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled)
                   VALUES('organiser_section',?,?, '📆 Calendar',1,1)""",
                (str(section_id), url),
            )
            connection.commit()
        syncer.enabled = True
        location = self.json_request('POST', '/api/locations', {'name': 'Test Ward', 'address': '1 Test Road'})
        area = self.json_request('POST', '/api/shift-types', {'name': 'Clinic'})
        day = (date.today() + timedelta(days=13)).isoformat()
        self.json_request('POST', '/api/shifts', {
            'work_date': day, 'location_id': location['id'], 'shift_type_id': area['id'],
            'start_time': '09:00', 'end_time': '17:00', 'break_minutes': 0,
        })
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Capture()
        logger = logging.getLogger('align.icloud')
        logger.addHandler(handler)
        try:
            syncer.sync()
        finally:
            logger.removeHandler(handler)
        self.assertFalse(any('shift-' in url for _, url in syncer.client.calls))
        self.assertTrue(any('shift push skipped' in message for message in records))
        self.assertNotIn('fake-test-password', '\n'.join(records))
        self.assertIn('no Work calendar', syncer.message)


if __name__ == '__main__':
    unittest.main()

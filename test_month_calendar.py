"""Month calendar boundary and event visibility regression tests."""
import unittest
from datetime import date
import app
from test_support import IsolatedAppServer

class MonthCalendarTests(unittest.TestCase):
    setUp = IsolatedAppServer.setUp
    tearDown = IsolatedAppServer.tearDown
    request = IsolatedAppServer.request
    json_request = IsolatedAppServer.json_request

    def test_month_grids_cover_whole_monday_sunday_weeks(self):
        for month, start, end in [('2024-02','2024-01-29','2024-03-03'), ('2027-02','2027-02-01','2027-02-28'), ('2026-12','2026-11-30','2027-01-03')]:
            result = self.json_request('GET', '/api/month?month=' + month)
            self.assertEqual((result['start'],result['end']), (start,end))
            self.assertEqual(result['events'], [])
            self.assertEqual(result['imported_events'], [])
            self.assertEqual((date.fromisoformat(end)-date.fromisoformat(start)).days % 7, 6)
        for month in ['2026-13','2026-00','not-a-month','2026-1']:
            self.json_request('GET', '/api/month?month=' + month, expected=400)

    def test_section_events_are_visible_without_legacy_schedule_rows(self):
        section_id = self.json_request('POST', '/api/sections', {'name': 'Personal'})['id']
        event = {'title': 'New Year appointment', 'start_at': '2026-12-31T10:00',
                 'end_at': '2026-12-31T10:45', 'location': 'Town Centre'}
        self.json_request('POST', f'/api/sections/{section_id}/events', event)
        result = self.json_request('GET', '/api/month?month=2026-12')
        self.assertEqual([item['title'] for item in result['events']], ['New Year appointment'])
        self.assertNotIn('shifts', result)
        self.assertNotIn('annual_leave', result)
        with app.db_connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM organiser_events').fetchone()[0], 1)

if __name__ == '__main__':
    unittest.main()

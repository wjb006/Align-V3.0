"""Month calendar boundary and event visibility regression tests."""
import unittest
from datetime import date
import app
from test_work_setup import WorkSetupTests

class MonthCalendarTests(unittest.TestCase):
    setUp = WorkSetupTests.setUp
    tearDown = WorkSetupTests.tearDown
    request = WorkSetupTests.request
    json_request = WorkSetupTests.json_request
    configuration = WorkSetupTests.configuration

    def test_month_grids_cover_whole_monday_sunday_weeks(self):
        for month, start, end in [('2024-02','2024-01-29','2024-03-03'), ('2027-02','2027-02-01','2027-02-28'), ('2026-12','2026-11-30','2027-01-03')]:
            result = self.json_request('GET', '/api/month?month=' + month)
            self.assertEqual((result['start'],result['end']), (start,end))
            self.assertEqual(result['shifts'], [])
            self.assertEqual((date.fromisoformat(end)-date.fromisoformat(start)).days % 7, 6)
        for month in ['2026-13','2026-00','not-a-month','2026-1']:
            self.json_request('GET', '/api/month?month=' + month, expected=400)

    def test_shifts_leave_and_colours_are_visible_without_writes(self):
        self.json_request('PUT', '/api/work-setup', self.configuration())
        template = next(t for t in self.json_request('GET', '/api/bootstrap')['master']['templates'] if t['shift_type_name']=='Wards')
        self.json_request('POST', '/api/shifts', {'shifts':[{'work_date':'2026-12-31','template_id':template['id']}]})
        with app.db_connection() as connection:
            connection.execute("INSERT INTO annual_leave(leave_date,notes) VALUES('2027-01-01','Test')")
        before = self.json_request('GET', '/api/shifts')
        result = self.json_request('GET', '/api/month?month=2026-12')
        self.assertEqual(len(result['shifts']),1)
        self.assertEqual(result['shifts'][0]['location_colour'], '#23AA88')
        self.assertEqual(result['annual_leave'][0]['leave_date'], '2027-01-01')
        self.assertEqual(self.json_request('GET', '/api/shifts'),before)

if __name__ == '__main__':
    unittest.main()

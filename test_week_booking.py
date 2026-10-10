"""Weekly confirmations, live colour metadata and overnight collision checks."""
import copy
import unittest
from datetime import date, timedelta

import app
from test_work_setup import WorkSetupTests


class WeekBookingTests(unittest.TestCase):
    setUp = WorkSetupTests.setUp
    tearDown = WorkSetupTests.tearDown
    request = WorkSetupTests.request
    json_request = WorkSetupTests.json_request
    configuration = WorkSetupTests.configuration

    def configured(self):
        config = self.configuration()
        config['areas'][0]['colour'] = '#B73576'
        config['areas'][1]['colour'] = '#815BD1'
        self.json_request('PUT', '/api/work-setup', config)
        return self.json_request('GET', '/api/bootstrap')['master']['templates']

    def test_confirm_is_idempotent_and_updates_calendar(self):
        template = self.configured()[0]
        payload = {'request_id': 'weekly-confirm-123456', 'shifts': [
            {'work_date': '2030-01-07', 'template_id': template['id']},
            {'work_date': '2030-01-08', 'template_id': template['id']}]}
        first = self.json_request('POST', '/api/shifts', payload)
        self.assertEqual(first, self.json_request('POST', '/api/shifts', payload))
        self.assertEqual(len(self.json_request('GET', '/api/shifts')), 2)
        body = self.request('GET', '/api/calendars/live.ics')[2]
        self.assertEqual(body.count(b'BEGIN:VEVENT'), 2)
        self.assertNotIn(b'Rest Day', body)
        payload['shifts'][0]['work_date'] = '2030-01-09'
        self.assertIn('different week', self.json_request('POST', '/api/shifts', payload, expected=400)['error'])

    def test_invalid_confirmation_rolls_back_whole_week(self):
        template = self.configured()[0]
        payload = {'request_id': 'weekly-confirm-bad123', 'shifts': [
            {'work_date': '2030-01-07', 'template_id': template['id']},
            {'work_date': '2030-01-07', 'template_id': template['id']}]}
        self.json_request('POST', '/api/shifts', payload, expected=400)
        self.assertEqual(self.json_request('GET', '/api/shifts'), [])
        with app.db_connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM shift_batches').fetchone()[0], 0)

    def test_week_date_normalisation_and_leave(self):
        self.json_request('POST', '/api/leave', {'leave_date': '2027-01-01'})
        week = self.json_request('GET', '/api/week?start=2027-01-01')
        self.assertEqual((week['start'], week['end']), ('2026-12-28', '2027-01-03'))
        self.assertEqual(week['annual_leave'][0]['leave_date'], '2027-01-01')
        self.assertEqual(self.json_request('GET', '/api/week?start=2027-01-04')['annual_leave'], [])
        self.json_request('GET', '/api/week?start=bad', expected=400)

    def test_manual_any_date_can_use_saved_template(self):
        template = self.configured()[0]
        result = self.json_request('POST', '/api/shifts', {
            'allow_any_date': True,
            'shifts': [{'work_date': '2030-01-06', 'template_id': template['id']}]
        })
        self.assertEqual(result['shifts'][0]['work_date'], '2030-01-06')

    def test_user_can_change_both_colours_without_changing_shift_details(self):
        template = self.configured()[0]
        self.json_request('POST', '/api/shifts', {'shifts':[{'work_date':'2030-01-07','template_id':template['id']}]})
        before = self.json_request('GET','/api/shifts')[0]
        self.json_request('PUT','/api/user-colours', {
            'locations':[{'id':template['location_id'],'colour':'#116633'}],
            'shift_types':[{'id':template['shift_type_id'],'colour':'#990022'}]})
        after = self.json_request('GET','/api/week?start=2030-01-07')['shifts'][0]
        self.assertEqual((after['location_colour'],after['shift_type_colour']), ('#116633','#990022'))
        for key in ('id','work_date','start_time','end_time','hours','notes','colour'):
            self.assertEqual(after[key], before[key])
        saved = self.json_request('GET','/api/work-setup')
        self.assertIn('#990022', [a['colour'] for a in saved['areas']])
        self.json_request('PUT','/api/user-colours', {'locations':[{'id':template['location_id'],'colour':'#ffffff'}], 'shift_types':[{'id':template['shift_type_id'],'colour':'bad'}]}, expected=400)
        self.assertEqual(self.json_request('GET','/api/shifts')[0]['location_colour'], '#116633')

    def test_overnight_checks_adjacent_days_and_edits(self):
        template = self.configured()[0]
        def shift(day, start, end):
            return {'work_date':day,'template_id':template['id'],'start_time':start,'end_time':end}
        self.json_request('POST','/api/shifts', {'shifts':[shift('2030-01-07','22:00','06:00')]})
        self.json_request('POST','/api/shifts', {'shifts':[shift('2030-01-08','05:00','09:00')]}, expected=400)
        added = self.json_request('POST','/api/shifts', {'shifts':[shift('2030-01-08','06:00','10:00')]})['shifts'][0]
        self.json_request('PUT',f"/api/shifts/{added['id']}", {**added,'start_time':'05:00'}, expected=400)
        self.assertEqual(len(self.json_request('GET','/api/shifts')),2)

    def test_no_seeded_personal_data(self):
        app.initialise_database()
        boot = self.json_request('GET','/api/bootstrap')
        self.assertEqual(boot['settings']['user_name'], '')
        self.assertFalse(boot['settings']['onboarding_completed'])
        self.assertEqual(boot['master']['locations'], [])
        self.assertEqual(boot['master']['shift_types'], [])
        self.assertEqual(boot['master']['templates'], [])
        self.assertEqual(self.json_request('GET','/api/shifts'), [])
        self.assertIn('colours', [b['branch_type'] for b in boot['master']['branches']])


if __name__ == '__main__':
    unittest.main()

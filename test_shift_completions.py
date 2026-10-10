"""Week hours, leave balance, appointment clashes, cover, and leave-at alerts."""
import gc
import sqlite3
import unittest
from datetime import date, datetime, timedelta

import app
from test_calendar_sync import CalendarSyncTests
from test_work_setup import WorkSetupTests


class ShiftCompletionTests(unittest.TestCase):
    setUp = CalendarSyncTests.setUp
    tearDown = CalendarSyncTests.tearDown
    request = CalendarSyncTests.request
    json_request = CalendarSyncTests.json_request
    create_shift = CalendarSyncTests.create_shift

    def week_summary(self):
        return self.json_request('GET', f'/api/week?start={self.day}')['summary']

    def test_overtime_uses_contracted_hours_and_rate(self):
        self.json_request('PUT', '/api/user-settings', {'contracted_hours': 30, 'rate_of_pay': 20})
        self.create_shift()
        summary = self.week_summary()
        self.assertEqual(summary['week_hours'], 4)
        self.assertEqual(summary['regular_hours'], 4)
        self.assertEqual(summary['overtime_hours'], 0)
        self.assertEqual(summary['pay_estimate'], 80)
        self.assertEqual(summary['contracted_hours'], 30)

    def test_hours_above_contract_are_overtime(self):
        self.json_request('PUT', '/api/user-settings', {'contracted_hours': 2, 'rate_of_pay': 10})
        self.create_shift()
        summary = self.week_summary()
        self.assertEqual(summary['regular_hours'], 2)
        self.assertEqual(summary['overtime_hours'], 2)
        self.assertEqual(summary['pay_estimate'], 40)

    def test_given_away_shift_stays_visible_and_leaves_the_hours(self):
        self.json_request('PUT', '/api/user-settings', {'contracted_hours': 10, 'rate_of_pay': 15})
        shift = self.create_shift()
        self.json_request('PUT', f"/api/shifts/{shift['id']}", {**shift, 'cover': 'given', 'cover_name': 'Sam'})
        saved = self.json_request('GET', '/api/shifts')[0]
        self.assertIn('[Align cover: given Sam]', saved['notes'])
        summary = self.week_summary()
        self.assertEqual(summary['shift_count'], 1)
        self.assertEqual(summary['week_hours'], 0)
        self.assertEqual(summary['pay_estimate'], 0)
        self.json_request('PUT', f"/api/shifts/{shift['id']}", {**saved, 'cover': ''})
        cleared = self.json_request('GET', '/api/shifts')[0]
        self.assertNotIn('[Align cover:', cleared['notes'])
        self.assertEqual(self.week_summary()['week_hours'], 4)

    def test_saved_journey_sets_the_leave_alert(self):
        leave = datetime.fromisoformat(f'{self.day}T06:40')
        notes = f"[Align travel]\nLeave home: {leave.strftime('%d %b %H:%M')}\napproximately 35 minutes travelling\n[/Align travel]"
        shift = self.create_shift(notes=notes)
        alerts = self.json_request('GET', '/api/dashboard')['alerts']
        match = next(alert for alert in alerts if alert['shift_id'] == shift['id'] and alert['title'].startswith('Leave at'))
        self.assertEqual(match['alert_at'], leave.isoformat(timespec='minutes'))
        self.assertNotIn('Time to Leave', [alert['title'] for alert in alerts if alert['shift_id'] == shift['id']])

    def test_own_appointment_blocks_a_shift(self):
        section = self.json_request('POST', '/api/sections', {'name': 'Appointments'})['id']
        self.json_request('POST', f'/api/sections/{section}/events', {
            'title': 'Dentist',
            'start_at': f'{self.day}T08:00',
            'end_at': f'{self.day}T09:00',
        })
        error = self.json_request('POST', '/api/shifts', {'shifts': [{
            'work_date': self.day, 'template_id': self.pattern,
            'start_time': '07:30', 'end_time': '11:30', 'break_minutes': 0,
        }]}, expected=400)
        self.assertIn('Dentist', error['error'])
        later = (date.fromisoformat(self.day) + timedelta(days=1)).isoformat()
        self.json_request('POST', '/api/shifts', {'shifts': [{
            'work_date': later, 'template_id': self.pattern,
            'start_time': '07:30', 'end_time': '11:30', 'break_minutes': 0,
        }]})

    def test_leave_allowance_counts_the_leave_year(self):
        self.json_request('PUT', '/api/user-settings', {'leave_allowance_days': 10, 'leave_year_start': '01-01'})
        booked = self.json_request('POST', '/api/leave', {'start_date': self.day, 'end_date': self.day})
        self.assertEqual(booked['leave_balance']['booked'], 1)
        self.assertEqual(booked['leave_balance']['remaining'], 9)
        self.assertEqual(self.json_request('GET', '/api/dashboard')['leave_balance']['allowance'], 10)

    def test_leave_year_clamps_29_february(self):
        start, end = app.leave_year_bounds(date(2023, 3, 1), '02-29')
        self.assertEqual(start, date(2023, 2, 28))
        self.assertEqual(end, date(2024, 2, 28))
        leap_start, _ = app.leave_year_bounds(date(2024, 3, 1), '02-29')
        self.assertEqual(leap_start, date(2024, 2, 29))


class WorkSettingsLeaveFields(unittest.TestCase):
    setUp = WorkSetupTests.setUp
    tearDown = WorkSetupTests.tearDown
    request = WorkSetupTests.request
    json_request = WorkSetupTests.json_request
    configuration = WorkSetupTests.configuration

    def test_hours_save_keeps_leave_and_rest(self):
        payload = self.configuration()
        payload.update(leave_allowance_days=27, leave_year_start='04-01', minimum_rest_hours=11)
        self.json_request('PUT', '/api/work-setup', payload)
        saved = self.json_request('GET', '/api/work-setup')
        self.assertEqual(saved['leave_allowance_days'], 27)
        self.assertEqual(saved['leave_year_start'], '04-01')
        self.assertEqual(saved['minimum_rest_hours'], 11)
        self.assertEqual(self.json_request('GET', '/api/bootstrap')['settings']['leave_allowance_days'], 27)


class MissingSettingsTests(unittest.TestCase):
    def test_dashboard_settings_default_when_rows_are_absent(self):
        connection = sqlite3.connect(':memory:')
        connection.row_factory = sqlite3.Row
        connection.execute('CREATE TABLE settings(setting_key TEXT PRIMARY KEY, setting_value TEXT)')
        settings = app.get_settings(connection)
        self.assertEqual(settings['contracted_hours'], 0)
        self.assertEqual(settings['rate_of_pay'], 0)
        self.assertTrue(settings['notifications'])
        self.assertEqual(settings['minimum_rest_hours'], 0)
        self.assertEqual(settings['leave_allowance_days'], 0)
        self.assertEqual(settings['user_name'], '')


if __name__ == '__main__':
    unittest.main()

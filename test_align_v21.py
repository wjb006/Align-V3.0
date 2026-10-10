"""Align V2.1 helpers: travel calendar notes, leave alerts, and defaults."""
import unittest
from datetime import datetime

import travel_calendar
import travel_reminders
import owner_builder


class TravelCalendarV21Tests(unittest.TestCase):
    def test_leave_alert_title_matches_spec(self):
        title = travel_calendar.leave_alert_title(datetime(2026, 10, 6, 10, 0), 'Clinic')
        self.assertEqual(title, 'Leave at 10:00 for "Clinic"')

    def test_calendar_description_formats_travel_bullets(self):
        notes = (
            "[Align travel]\n"
            "Leave home: 06 Oct 10:00\n"
            "Arrive at event location: 10:25 · Event: 10:30\n"
            "Bus from home · approximately 25 minutes travelling\n"
            "Bus 418 towards Eastham · Bidston 10:12 → Eastham 10:22\n"
            "[/Align travel]"
        )
        text = travel_calendar.calendar_description(notes)
        self.assertIn('- Leave: 10:00', text)
        self.assertIn('- Bus/train: 10:12 Bus 418 Eastham', text)
        self.assertIn('- Arrive: 10:25', text)

    def test_plan_accepts_current_location_wording(self):
        start = datetime(2026, 10, 6, 10, 30)
        plan = travel_calendar.plan(
            'Leave current location: 06 Oct 10:00\napproximately 20 minutes travelling',
            start,
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan[0], datetime(2026, 10, 6, 10, 0))
        self.assertEqual(plan[1], 20)


class AlertOffsetTests(unittest.TestCase):
    def test_offsets_include_minutes_hours_days_week(self):
        values = [item[0] for item in travel_reminders.ALERT_OFFSETS]
        self.assertEqual(values, [5, 10, 15, 30, 45, 60, 120, 1440, 2880, 7200, 10080])
        self.assertEqual(travel_reminders.label(10080), '1 week before')


class UpcomingEventsDefaultTests(unittest.TestCase):
    def test_default_home_section_title(self):
        class Connection:
            def execute(self, *args, **kwargs):
                return []
        doc = owner_builder.defaults(Connection())
        upcoming = next(section for section in doc['home_sections'] if section['id'] == 'upcoming')
        self.assertEqual(upcoming['title'], 'Upcoming Events')


if __name__ == '__main__':
    unittest.main()

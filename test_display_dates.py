"""User-facing dates are DD/MM/YYYY. Stored and API values stay ISO."""
import sqlite3
import unittest
from datetime import datetime

import travel_calendar
from display_dates import format_display_date, format_display_datetime


class DisplayDates(unittest.TestCase):
    def test_date_and_datetime_formats(self):
        self.assertEqual(format_display_date("2026-10-07"), "07/10/2026")
        self.assertEqual(format_display_date(datetime(2026, 10, 7, 14, 5)), "07/10/2026")
        self.assertEqual(format_display_datetime(datetime(2026, 10, 7, 6, 40)), "07/10/2026 06:40")
        self.assertEqual(format_display_datetime("2026-10-07T14:30:00"), "07/10/2026 14:30")
        self.assertEqual(format_display_datetime("2026-10-07T08:00:00Z"), "07/10/2026 09:00")
        self.assertEqual(format_display_date(""), "")

    def test_week_planner_endpoint_and_options_are_retired(self):
        import app
        self.assertFalse(hasattr(app, "next_week_options"))
        self.assertTrue(app.retired_schedule_endpoint("/api/week"))

    def test_numeric_leave_notes_still_parse(self):
        leave = datetime(2026, 10, 7, 6, 40)
        text = f"Leave home: {format_display_datetime(leave)}"
        self.assertEqual(text, "Leave home: 07/10/2026 06:40")
        start = datetime(2026, 10, 7, 8, 0)
        self.assertEqual(travel_calendar.plan(text, start)[0], leave)
        self.assertIn("06:40", travel_calendar.calendar_description(text))

    def test_invite_email_formats_expiry_for_people(self):
        import beta_email
        source = open(beta_email.__file__, encoding="utf-8").read()
        self.assertIn("format_display_datetime(expires_at)", source)


if __name__ == "__main__":
    unittest.main()

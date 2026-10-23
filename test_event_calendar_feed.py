"""The subscribed Align calendar publishes V3 events, retaining old rows privately."""
import tempfile
import unittest
from pathlib import Path

import app


class EventCalendarFeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="align-event-feed-")
        self.original_database = app.DATABASE
        app.DATABASE = Path(self.temp.name) / "events.sqlite3"
        app.initialise_database()

    def tearDown(self):
        app.DATABASE = self.original_database
        self.temp.cleanup()

    def test_feed_exports_timed_and_all_day_events_without_publishing_legacy_schedule(self):
        with app.db_connection() as connection:
            section_id = connection.execute(
                "INSERT INTO organiser_sections(name) VALUES('Personal')"
            ).lastrowid
            connection.execute(
                "INSERT INTO organiser_events(section_id,title,start_at,end_at,all_day,location,notes) "
                "VALUES(?,?,?,?,?,?,?)",
                (section_id, "Dentist, check-up", "2026-10-12T09:30", "2026-10-12T10:15", 0,
                 "Town Centre", "Bring insurance card"),
            )
            connection.execute(
                "INSERT INTO organiser_events(section_id,title,start_at,end_at,all_day) VALUES(?,?,?,?,?)",
                (section_id, "Annual review", "2026-10-13T00:00", "2026-10-14T00:00", 1),
            )
            feed = app.align_ics(connection).decode("utf-8")

        self.assertIn("X-WR-CALNAME:Align", feed)
        self.assertIn("UID:align-event-1@getalign.co.uk", feed)
        self.assertIn("DTSTART;TZID=Europe/London:20261012T093000", feed)
        self.assertIn("DTEND;TZID=Europe/London:20261012T101500", feed)
        self.assertIn("SUMMARY:Dentist\\, check-up", feed)
        self.assertIn("LOCATION:Town Centre", feed)
        self.assertIn("DESCRIPTION:Bring insurance card", feed)
        self.assertIn("DTSTART;VALUE=DATE:20261013", feed)
        self.assertIn("DTEND;VALUE=DATE:20261014", feed)
        self.assertNotIn("Annual leave", feed)
        self.assertNotIn("align-shift-", feed)


if __name__ == "__main__":
    unittest.main()

"""Integration checks use an isolated SQLite file, never the user's schedule."""
import gc
import json
import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import app


class QuietHandler(app.AlignHandler):
    def log_message(self, *args):
        pass


class CalendarSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="align-test-")
        self.original_database, self.original_password = app.DATABASE, app.ADMIN_PASSWORD
        app.DATABASE = Path(self.temp.name) / "test.sqlite3"
        app.ADMIN_PASSWORD = ""
        app.initialise_database()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.day = (date.today() + timedelta(days=14)).isoformat()
        self.location = self.json_request("POST", "/api/locations", {"name": "Test location", "address": "Road, Town"})["id"]
        self.kind = self.json_request("POST", "/api/shift-types", {"name": "Wards"})["id"]
        self.pattern = self.json_request("POST", "/api/templates", {
            "location_id": self.location, "shift_type_id": self.kind, "sub_shift_type": "AM",
            "start_time": "07:30", "end_time": "11:30", "applicable_days": list(app.WEEK_DAYS),
        })["id"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        app.DATABASE, app.ADMIN_PASSWORD = self.original_database, self.original_password
        gc.collect()
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        client.request(method, path, body=json.dumps(data) if data is not None else None,
                       headers={"Content-Type": "application/json", **(headers or {})})
        response = client.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        client.close()
        return result

    def json_request(self, method, path, data=None, expected=None):
        status, _, body = self.request(method, path, data)
        self.assertEqual(status, expected or (201 if method == "POST" else 200), body)
        return json.loads(body)

    def create_shift(self, **changes):
        payload = {"work_date": self.day, "template_id": self.pattern,
                   "start_time": "07:30", "end_time": "11:30", "break_minutes": 0, **changes}
        return self.json_request("POST", "/api/shifts", {"shifts": [payload]})["shifts"][0]

    def test_full_journey_notes_survive_create_edit_and_reopen(self):
        notes = '[Align travel]\nLeave home: 08:13\n' + ('Walking and bus detail. ' * 60) + '\n[/Align travel]\n[Align travel steps]\n[{"mode":"bus","service":"17"}]\n[/Align travel steps]'
        shift = self.create_shift(notes=notes)
        with app.db_connection() as c:
            self.assertEqual(c.execute('SELECT notes FROM shifts WHERE id=?', (shift['id'],)).fetchone()[0], notes)
        updated = notes + '\nBring pass'
        self.json_request('PUT', f"/api/shifts/{shift['id']}", {**shift, 'notes': updated})
        with app.db_connection() as c:
            self.assertEqual(c.execute('SELECT notes FROM shifts WHERE id=?', (shift['id'],)).fetchone()[0], updated)
        status, _, _ = self.request('PUT', f"/api/shifts/{shift['id']}", {**shift, 'notes': 'x' * 20001})
        self.assertEqual(status, 400)
        with app.db_connection() as c:
            self.assertEqual(c.execute('SELECT notes FROM shifts WHERE id=?', (shift['id'],)).fetchone()[0], updated)

    def test_feed_update_delete_and_conditional_refresh(self):
        shift = self.create_shift()
        status, headers, original = self.request("GET", "/api/calendars/live.ics")
        self.assertEqual(status, 200)
        self.assertNotIn("Content-Disposition", headers)
        self.assertIn(b"TRIGGER:-PT60M", original)
        self.assertIn(b"DESCRIPTION:Time to Leave", original)
        self.assertIn(b"DTSTAMP:", original)
        self.assertEqual(self.request("GET", "/api/calendars/live.ics", headers={"If-None-Match": headers["ETag"]})[0], 304)
        self.assertEqual(self.request("HEAD", "/api/calendars/live.ics")[2], b"")
        moved_day = (date.fromisoformat(self.day) + timedelta(days=1)).isoformat()
        self.json_request("PUT", f"/api/shifts/{shift['id']}", {**shift, "work_date": moved_day})
        _, changed_headers, changed = self.request("GET", "/api/calendars/live.ics")
        self.assertNotEqual(headers["ETag"], changed_headers["ETag"])
        uid = f"UID:align-shift-{shift['id']}@local".encode()
        self.assertIn(uid, original)
        self.assertIn(uid, changed)
        self.assertIn(f"DTSTART;TZID=Europe/London:{moved_day.replace('-', '')}T073000".encode(), changed)
        self.json_request("DELETE", f"/api/shifts/{shift['id']}")
        self.assertNotIn(uid, self.request("GET", "/api/calendars/live.ics")[2])

    def test_custom_alert_changes_existing_shifts(self):
        self.create_shift()
        rule = self.json_request("POST", "/api/alert-rules", {"title": "Get ready", "minutes_before": 90})
        feed = self.request("GET", "/api/calendars/live.ics")[2]
        self.assertIn(b"TRIGGER:-PT90M", feed)
        self.assertIn(b"DESCRIPTION:Get ready", feed)
        alerts = self.json_request("GET", "/api/dashboard")["alerts"]
        ready = next(alert for alert in alerts if alert["title"] == "Get ready")
        expected = datetime.fromisoformat(f"{self.day}T07:30") - timedelta(minutes=90)
        self.assertEqual(ready["alert_at"], expected.isoformat(timespec="minutes"))
        self.json_request("PUT", f"/api/alert-rules/{rule['id']}", {"title": "Get ready", "minutes_before": 30, "active": False})
        self.assertNotIn(b"DESCRIPTION:Get ready", self.request("GET", "/api/calendars/live.ics")[2])
        self.json_request("PUT", "/api/user-settings", {"notifications": False})
        self.assertNotIn(b"BEGIN:VALARM", self.request("GET", "/api/calendars/live.ics")[2])
        self.assertEqual(self.json_request("GET", "/api/dashboard")["alerts"], [])

    def test_saved_journey_becomes_travel_block_and_alert(self):
        leave = datetime.fromisoformat(f"{self.day}T06:40")
        notes = f"[Align travel]\nLeave home: {leave.strftime('%d %b %H:%M')}\nBus from home · approximately 35 minutes travelling\n[/Align travel]"
        shift = self.create_shift(notes=notes)
        feed = self.request("GET", "/api/calendars/live.ics")[2]
        self.assertIn(b"X-APPLE-TRAVEL-DURATION;VALUE=DURATION:PT35M", feed)
        self.assertIn(b"TRIGGER:-PT50M", feed)
        self.assertIn(b'Leave at 06:40 for "', feed)
        self.assertIn(b"- Leave: 06:40", feed)
        self.assertIn(f"UID:align-travel-{shift['id']}@local".encode(), feed)
        self.assertIn(b"TRIGGER:PT0S", feed)
        self.assertIn(f"DTSTART;TZID=Europe/London:{leave.strftime('%Y%m%dT%H%M%S')}".encode(), feed)
        self.assertIn(b"TRANSP:TRANSPARENT", feed)
        self.json_request("PUT", "/api/user-settings", {"notifications": False})
        quiet = self.request("GET", "/api/calendars/live.ics")[2]
        self.assertNotIn(b"X-APPLE-TRAVEL-DURATION", quiet)
        self.assertNotIn(b"align-travel-", quiet)

    def test_travel_calendar_parser_edges(self):
        import travel_calendar
        start = datetime(2027, 1, 1, 8, 0)
        self.assertEqual(travel_calendar.plan("Leave home: 31 Dec 23:30", start)[0], datetime(2026, 12, 31, 23, 30))
        self.assertIsNone(travel_calendar.plan("Leave home: 25 Dec 23:30", start))
        self.assertIsNone(travel_calendar.plan("no journey", start))

    def test_overnight_and_utf8_calendar_lines(self):
        self.create_shift(start_time="22:00", end_time="06:00", notes="Café; " * 40 + "\r\nNext line")
        feed = self.request("GET", "/api/calendars/align.ics")[2]
        next_day = (date.fromisoformat(self.day) + timedelta(days=1)).strftime("%Y%m%d")
        self.assertIn(f"DTEND;TZID=Europe/London:{next_day}T060000".encode(), feed)
        self.assertIn(b"TZID:Europe/London", feed)
        for line in feed.split(b"\r\n"):
            self.assertLessEqual(len(line), 75)
            line.decode("utf-8")

    def test_date_move_rejects_overlap_and_leave(self):
        shift = self.create_shift()
        next_day = (date.fromisoformat(self.day) + timedelta(days=1)).isoformat()
        self.create_shift(work_date=next_day)
        path = f"/api/shifts/{shift['id']}"
        rejected = self.json_request("PUT", path, {**shift, "work_date": next_day}, expected=400)
        self.assertIn("overlaps", rejected["error"])
        self.json_request("POST", "/api/leave", {"leave_date": self.day})
        self.assertIn("annual leave", self.json_request("PUT", path, shift, expected=400)["error"])

    def test_location_categories_and_multiple_saved_hours(self):
        clinic = self.json_request("POST", "/api/shift-types", {"name": "Clinic"})["id"]
        self.json_request("PUT", f"/api/user-locations/{self.location}", {
            "name": "Test location", "address": "Road", "shift_type_ids": [self.kind, clinic],
        })
        master = self.json_request("GET", "/api/master")
        self.assertEqual(set(master["location_categories"][str(self.location)]), {self.kind, clinic})
        self.json_request("POST", "/api/templates", {
            "location_id": self.location, "shift_type_id": self.kind, "sub_shift_type": "AM",
            "start_time": "08:00", "end_time": "12:00", "applicable_days": list(app.WEEK_DAYS),
        })
        self.assertEqual(len(self.json_request("GET", "/api/master")["templates"]), 2)


if __name__ == "__main__":
    unittest.main()

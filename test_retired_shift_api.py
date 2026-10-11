"""Retired schedule endpoints stay unavailable without deleting legacy records."""
import unittest

import app
from test_support import IsolatedAppServer


class RetiredShiftApiTests(unittest.TestCase):
    setUp = IsolatedAppServer.setUp
    tearDown = IsolatedAppServer.tearDown
    request = IsolatedAppServer.request

    def test_shift_schedule_and_fixed_work_setup_routes_are_retired(self):
        for path in (
            "/api/shifts",
            "/api/week?start=2026-10-12",
            "/api/annual-leave",
            "/api/work-setup",
            "/api/locations",
            "/api/shift-types",
            "/api/templates",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(self.request("POST", "/api/shifts", {})[0], 404)
        self.assertEqual(self.request("POST", "/api/annual-leave", {})[0], 404)

    def test_legacy_schedule_admin_writes_are_retired_before_database_access(self):
        retired_requests = (
            ("POST", "/api/locations", {}),
            ("PUT", "/api/locations/1", {"name": "Legacy"}),
            ("POST", "/api/shift-types", {"name": "Legacy"}),
            ("PUT", "/api/shift-types/1", {"name": "Legacy"}),
            ("POST", "/api/templates", {}),
            ("PUT", "/api/templates/1", {}),
            ("POST", "/api/templates/1/apply", {}),
            ("DELETE", "/api/locations/1", {}),
            ("DELETE", "/api/shift-types/1", {}),
            ("DELETE", "/api/templates/1", {}),
        )
        from unittest.mock import patch
        for method, path, payload in retired_requests:
            with self.subTest(method=method, path=path):
                # The route must be rejected before opening SQLite/Postgres. This
                # matters for a clean V3 database that has no schedule tables.
                with patch("app.db_connection", side_effect=AssertionError("database accessed")):
                    status, _, body = self.request(method, path, payload)
                self.assertEqual(status, 404)
                self.assertIn("no longer available", body.decode("utf-8").lower())

    def test_reinitializing_the_schema_keeps_legacy_schedule_data(self):
        with app.db_connection() as connection:
            connection.execute(
                "INSERT INTO shifts(work_date,location_name,shift_type_name,colour,start_time,end_time,hours) "
                "VALUES('2026-10-12','Old location','AM','#365CE6','08:00','12:00',4)"
            )
            connection.execute(
                "INSERT INTO annual_leave(leave_date,notes) VALUES('2026-10-13','Keep for recovery')"
            )

        app.initialise_database()

        with app.db_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM shifts").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT notes FROM annual_leave").fetchone()[0], "Keep for recovery")


if __name__ == "__main__":
    unittest.main()

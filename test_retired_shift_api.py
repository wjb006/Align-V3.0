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
            ("GET", "/api/shifts", {}),
            ("GET", "/api/week?start=2026-10-12", {}),
            ("GET", "/api/annual-leave", {}),
            ("GET", "/api/work-setup", {}),
            ("POST", "/api/shifts", {}),
            ("POST", "/api/annual-leave", {}),
            ("PUT", "/api/shifts/1", {}),
            ("DELETE", "/api/shifts/1", {}),
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

    def test_v3_storage_validator_does_not_require_retired_schedule_tables(self):
        from postgres_support import validate_v3_storage

        class RecordingConnection:
            def __init__(self):
                self.statements = []

            def execute(self, statement):
                self.statements.append(statement)
                if any(table in statement for table in (
                    "shifts", "shift_templates", "locations", "shift_types",
                    "annual_leave", "alert_rules", "shift_batches",
                )):
                    raise AssertionError("V3 validator queried a retired schedule table")

        connection = RecordingConnection()
        validate_v3_storage(connection)
        self.assertTrue(connection.statements)
        self.assertTrue(all("LIMIT 0" in statement for statement in connection.statements))

    def test_fresh_local_v3_schema_has_no_legacy_schedule_tables(self):
        with app.db_connection() as connection:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            self.assertTrue({'personal_items', 'organiser_events', 'assets',
                             'transport_preferences', 'transport_journey_cache'} <= tables)
            self.assertFalse(tables & {'locations', 'shift_types', 'location_shift_types',
                                       'shift_templates', 'shifts', 'shift_batches',
                                       'annual_leave', 'alerts', 'alert_rules'})
            settings = app.get_settings(connection)
            self.assertNotIn('contracted_hours', settings)
            self.assertNotIn('leave_allowance_days', settings)

    def test_reinitializing_the_schema_keeps_legacy_schedule_data(self):
        with app.db_connection() as connection:
            # Model an existing pre-V3 database before proving its records survive reinitialisation.
            connection.executescript((app.ROOT / 'schema.sql').read_text(encoding='utf-8'))
            connection.execute(
                "INSERT INTO shifts(work_date,location_name,shift_type_name,colour,start_time,end_time,hours) "
                "VALUES('2026-10-12','Old location','AM','#365CE6','08:00','12:00',4)"
            )
            location_id = connection.execute(
                "INSERT INTO locations(name,address) VALUES('Legacy clinic','Legacy address')"
            ).lastrowid
            type_id = connection.execute(
                "INSERT INTO shift_types(name) VALUES('Legacy AM')"
            ).lastrowid
            template_id = connection.execute(
                """INSERT INTO shift_templates(location_id,shift_type_id,label,sub_shift_type,start_time,end_time,applicable_days)
                   VALUES(?,?,?,?,?,?,?)""",
                (location_id, type_id, 'Keep this template', 'AM', '08:30', '12:30', '["Monday"]'),
            ).lastrowid
            connection.execute(
                "INSERT INTO settings(setting_key,setting_value) VALUES('contracted_hours','37') "
                "ON CONFLICT(setting_key) DO UPDATE SET setting_value='37'"
            )
            connection.execute(
                "INSERT INTO settings(setting_key,setting_value) VALUES('user_name','Your schedule') "
                "ON CONFLICT(setting_key) DO UPDATE SET setting_value='Your schedule'"
            )
            connection.execute(
                "INSERT INTO annual_leave(leave_date,notes) VALUES('2026-10-13','Keep for recovery')"
            )

        app.initialise_database()

        with app.db_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM shifts").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT notes FROM annual_leave").fetchone()[0], "Keep for recovery")
            template = connection.execute("SELECT label,sub_shift_type,applicable_days FROM shift_templates WHERE id=?", (template_id,)).fetchone()
            self.assertEqual(tuple(template), ('Keep this template', 'AM', '["Monday"]'))
            settings = {row['setting_key']:row['setting_value'] for row in connection.execute(
                "SELECT setting_key,setting_value FROM settings WHERE setting_key IN ('contracted_hours','user_name')"
            )}
            self.assertEqual(settings, {'contracted_hours':'37','user_name':'Your schedule'})


if __name__ == "__main__":
    unittest.main()

"""Work Settings persistence and planner-data preservation regressions."""
import unittest

import app
import planner_api
import work_setup
from test_support import IsolatedAppServer


class WorkSetupPersistenceTests(IsolatedAppServer, unittest.TestCase):
    def _initial_payload(self):
        with app.db_connection() as connection:
            setup = work_setup.load_setup(connection)
        return {
            "revision": setup["revision"],
            "contracted_hours": 37.5,
            "rate_of_pay": 15.25,
            "duration_minutes": 240,
            "leave_allowance_days": 30,
            "leave_year_start": "04-01",
            "minimum_rest_hours": 11,
            "slots": [
                {"key": "am", "start_time": "08:30", "duration_minutes": 240, "break_minutes": 0},
                {"key": "pm", "start_time": "13:00", "duration_minutes": 240, "break_minutes": 30},
            ],
            "locations": [
                {"key": "arrowe", "name": "Arrowe Park", "address": "Arrowe Park Road, Wirral", "colour": "#365CE6"},
                {"key": "clatterbridge", "name": "Clatterbridge", "address": "Clatterbridge Road, Wirral", "colour": "#16A085"},
            ],
            "areas": [
                {"key": "ward", "name": "Wards", "colour": "#3B82F6", "slots": ["am"]},
                {"key": "clinic", "name": "Clinic", "colour": "#8B5CF6", "slots": ["am", "pm"]},
            ],
            "assignments": [
                {"location_key": "arrowe", "area_key": "ward", "slot_key": "am", "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]},
                {"location_key": "arrowe", "area_key": "clinic", "slot_key": "am", "days": ["Monday", "Wednesday", "Friday"]},
                {"location_key": "clatterbridge", "area_key": "clinic", "slot_key": "pm", "days": ["Tuesday", "Thursday"]},
            ],
        }

    def test_multiple_workplaces_areas_and_patterns_survive_reopen(self):
        with app.db_connection() as connection:
            result = work_setup.save_setup(connection, self._initial_payload())
            connection.commit()
            self.assertEqual(result["patterns"], 3)

        with app.db_connection() as connection:
            saved = work_setup.load_setup(connection)
        self.assertEqual(saved["contracted_hours"], 37.5)
        self.assertEqual(saved["rate_of_pay"], 15.25)
        self.assertEqual(saved["leave_allowance_days"], 30)
        self.assertEqual(saved["leave_year_start"], "04-01")
        self.assertEqual(saved["minimum_rest_hours"], 11)
        self.assertEqual({item["name"] for item in saved["locations"]}, {"Arrowe Park", "Clatterbridge"})
        self.assertEqual({item["name"] for item in saved["areas"]}, {"Wards", "Clinic"})
        self.assertEqual(len(saved["assignments"]), 3)
        ward = next(item for item in saved["areas"] if item["name"] == "Wards")
        arrowe = next(item for item in saved["locations"] if item["name"] == "Arrowe Park")
        assignment = next(item for item in saved["assignments"]
                          if item["area_key"] == ward["key"] and item["location_key"] == arrowe["key"])
        self.assertEqual(
            assignment["days"],
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        )

    def test_work_settings_edits_do_not_rewrite_existing_shifts(self):
        with app.db_connection() as connection:
            work_setup.save_setup(connection, self._initial_payload())
            connection.commit()
            template = connection.execute(
                "SELECT id,location_id,shift_type_id FROM shift_templates WHERE active=1 ORDER BY id LIMIT 1"
            ).fetchone()
            values = planner_api._shift_values(connection, {
                "work_date": self.day,
                "template_id": template["id"],
                "notes": "Existing planner entry",
            })
            shift_id = connection.execute(
                """INSERT INTO shifts(work_date,template_id,location_id,shift_type_id,location_name,
                   shift_type_name,colour,start_time,end_time,break_minutes,hours,notes)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            ).lastrowid
            connection.commit()

        with app.db_connection() as connection:
            before = dict(connection.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone())
            revised = work_setup.load_setup(connection)
            revised["contracted_hours"] = 40
            revised["rate_of_pay"] = 16.50
            work_setup.save_setup(connection, revised)
            connection.commit()

        with app.db_connection() as connection:
            after = dict(connection.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone())
            saved = work_setup.load_setup(connection)
        self.assertEqual(after, before)
        self.assertEqual(saved["contracted_hours"], 40)
        self.assertEqual(saved["rate_of_pay"], 16.5)

    def test_invalid_work_setup_is_rejected_without_persisting_partial_changes(self):
        with app.db_connection() as connection:
            payload = self._initial_payload()
            payload["locations"][0]["address"] = ""
            with self.assertRaises(ValueError):
                work_setup.save_setup(connection, payload)
            connection.rollback()

        with app.db_connection() as connection:
            saved = work_setup.load_setup(connection)
        self.assertEqual(saved["locations"], [])
        self.assertEqual(saved["areas"], [])


if __name__ == "__main__":
    import unittest
    unittest.main()

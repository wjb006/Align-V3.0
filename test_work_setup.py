"""Work Settings API regression tests for the restored planner."""
import unittest

from test_support import IsolatedAppServer


class WorkSetupApiTests(IsolatedAppServer, unittest.TestCase):

    def test_manual_work_settings_save_and_reload(self):
        original = self.json_request("GET", "/api/work-setup")
        payload = {
            **original,
            "contracted_hours": 37.5,
            "duration_minutes": 240,
            "rate_of_pay": 18.25,
            "leave_allowance_days": 27,
            "leave_year_start": "04-01",
            "minimum_rest_hours": 11,
            "slots": [],
            "locations": [{
                "key": "l-new",
                "name": "Arrowe Park",
                "address": "Arrowe Park Road, Upton",
                "colour": "#365CE6",
            }],
            "areas": [{
                "key": "a-new",
                "name": "Wards",
                "colour": "#3B82F6",
                "slots": [],
            }],
            "assignments": [],
            "save_mode": "settings",
        }
        saved = self.json_request("PUT", "/api/work-setup", payload)
        self.assertEqual(saved["patterns"], 0)
        loaded = self.json_request("GET", "/api/work-setup")
        self.assertEqual(loaded["contracted_hours"], 37.5)
        self.assertEqual(loaded["rate_of_pay"], 18.25)
        self.assertEqual(loaded["leave_allowance_days"], 27)
        self.assertEqual(loaded["leave_year_start"], "04-01")
        self.assertEqual(loaded["minimum_rest_hours"], 11)
        self.assertEqual([item["name"] for item in loaded["locations"]], ["Arrowe Park"])
        self.assertEqual([item["name"] for item in loaded["areas"]], ["Wards"])

    def test_multiple_workplaces_areas_and_weekday_patterns_persist(self):
        original = self.json_request("GET", "/api/work-setup")
        payload = {
            **original,
            "contracted_hours": 37.5,
            "duration_minutes": 240,
            "rate_of_pay": 18.25,
            "leave_allowance_days": 27,
            "leave_year_start": "04-01",
            "minimum_rest_hours": 11,
            "slots": [
                {"key": "am", "start_time": "08:30", "duration_minutes": 240, "break_minutes": 0},
                {"key": "pm", "start_time": "13:00", "duration_minutes": 240, "break_minutes": 30},
            ],
            "locations": [
                {"key": "arrowe", "name": "Arrowe Park", "address": "Arrowe Park Road, Upton", "colour": "#365CE6"},
                {"key": "clatterbridge", "name": "Clatterbridge", "address": "Clatterbridge Road, Wirral", "colour": "#16A085"},
            ],
            "areas": [
                {"key": "wards", "name": "Wards", "colour": "#3B82F6", "slots": ["am"]},
                {"key": "clinic", "name": "Clinic", "colour": "#8B5CF6", "slots": ["am", "pm"]},
            ],
            "assignments": [
                {"location_key": "arrowe", "area_key": "wards", "slot_key": "am",
                 "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]},
                {"location_key": "arrowe", "area_key": "clinic", "slot_key": "am",
                 "days": ["Monday", "Wednesday", "Friday"]},
                {"location_key": "clatterbridge", "area_key": "clinic", "slot_key": "pm",
                 "days": ["Tuesday", "Thursday"]},
            ],
            "save_mode": "settings",
        }
        saved = self.json_request("PUT", "/api/work-setup", payload)
        self.assertEqual(saved["patterns"], 3)

        loaded = self.json_request("GET", "/api/work-setup")
        self.assertEqual({item["name"] for item in loaded["locations"]}, {"Arrowe Park", "Clatterbridge"})
        self.assertEqual({item["name"] for item in loaded["areas"]}, {"Wards", "Clinic"})
        self.assertEqual(len(loaded["assignments"]), 3)
        self.assertEqual(loaded["contracted_hours"], 37.5)
        self.assertEqual(loaded["rate_of_pay"], 18.25)
        self.assertEqual(loaded["leave_allowance_days"], 27)
        self.assertEqual(loaded["leave_year_start"], "04-01")
        self.assertEqual(loaded["minimum_rest_hours"], 11)

        wards = next(item for item in loaded["areas"] if item["name"] == "Wards")
        arrowe = next(item for item in loaded["locations"] if item["name"] == "Arrowe Park")
        pattern = next(item for item in loaded["assignments"]
                       if item["area_key"] == wards["key"] and item["location_key"] == arrowe["key"])
        self.assertEqual(pattern["days"], ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])

    def test_stale_work_settings_revision_is_rejected(self):
        original = self.json_request("GET", "/api/work-setup")
        payload = {
            **original,
            "contracted_hours": 37.5,
            "duration_minutes": 240,
            "slots": [],
            "locations": [],
            "areas": [],
            "assignments": [],
            "save_mode": "settings",
            "revision": "stale-revision",
        }
        self.json_request("PUT", "/api/work-setup", payload, expected=400)


if __name__ == "__main__":
    unittest.main()

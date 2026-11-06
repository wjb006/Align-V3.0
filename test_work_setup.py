"""Work Settings API regression tests for the restored planner."""
import unittest

from test_support import IsolatedAppServer


class WorkSetupApiTests(unittest.TestCase):
    setUp = IsolatedAppServer.setUp
    tearDown = IsolatedAppServer.tearDown
    json_request = IsolatedAppServer.json_request

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

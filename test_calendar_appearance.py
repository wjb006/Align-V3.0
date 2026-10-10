import unittest
import appearance_settings as a


class CalendarAppearanceTests(unittest.TestCase):
    def test_defaults_include_calendar_and_fonts(self):
        r = a.validate_appearance({})
        self.assertEqual(r["calendar"]["week_headings"], "show")
        self.assertEqual(r["type"]["font"], "system")
        self.assertFalse(a.DEFAULT_PERMISSIONS["calendar"])

    def test_accepts_valid_calendar_and_type_options(self):
        r = a.validate_appearance({"calendar": {"month_cell": "#AABBCC", "week_headings": "hide"},
                                   "type": {"font": "serif", "heading": "normal"}})
        self.assertEqual(r["calendar"]["month_cell"], "#aabbcc")
        self.assertEqual(r["calendar"]["week_headings"], "hide")
        self.assertEqual(r["type"]["font"], "serif")
        events = a.validate_appearance({"events": {"location_banner": "off", "time_place": "right", "time_size": "standard", "title_format": "area"}})
        self.assertEqual(events["events"]["location_banner"], "off")
        self.assertEqual(events["events"]["title_format"], "area")
        self.assertEqual(a.validate_appearance({})["events"]["time_place"], "left")

    def test_rejects_invalid_values(self):
        for bad in ({"calendar": {"month_cell": "red"}}, {"calendar": {"week_headings": "x"}},
                    {"type": {"font": "comic"}}, {"type": {"heading": "x"}}, {"calendar": {"nope": "#000000"}}):
            with self.assertRaises(ValueError):
                a.validate_appearance(bad)

    def test_user_override_needs_permission(self):
        with self.assertRaises(ValueError):
            a.validate_user_overrides({"calendar": {"month_cell": "#112233"}}, a.DEFAULT_PERMISSIONS)
        ok = a.validate_user_overrides({"calendar": {"month_cell": "#112233"}}, {**a.DEFAULT_PERMISSIONS, "calendar": True})
        self.assertEqual(ok["calendar"]["month_cell"], "#112233")


if __name__ == "__main__":
    unittest.main()

"""Local GitHub update used by the Management Studio Update button."""
import subprocess
import unittest
from unittest.mock import patch

import studio_update


class StudioUpdateTests(unittest.TestCase):
    def test_fast_forward_reports_a_change_and_updates_the_database(self):
        calls = []

        def fake_git(*args):
            calls.append(args)
            if args == ("rev-parse", "HEAD"):
                text = "before\n" if len(calls) == 1 else "after\n"
            else:
                self.assertEqual(args, ("pull", "--ff-only", "origin", "main"))
                text = "Updating before..after\n"
            return subprocess.CompletedProcess(["git", *args], 0, text, "")

        started = []
        with patch.object(studio_update, "_git", side_effect=fake_git):
            result = studio_update.update_from_github(lambda: started.append(True))
        self.assertTrue(result["changed"])
        self.assertIn("Restart Management Studio", result["summary"])
        self.assertEqual(started, [True])
        self.assertIn(("pull", "--ff-only", "origin", "main"), calls)

    def test_already_current_does_not_touch_the_database(self):
        def fake_git(*args):
            text = "same\n" if args[0] == "rev-parse" else "Already up to date.\n"
            return subprocess.CompletedProcess(["git", *args], 0, text, "")

        with patch.object(studio_update, "_git", side_effect=fake_git):
            result = studio_update.update_from_github(lambda: self.fail("database"))
        self.assertFalse(result["changed"])
        self.assertEqual(result["summary"], "Already up to date.")

    def test_rejected_pull_is_reported(self):
        def fake_git(*args):
            if args[0] == "rev-parse":
                return subprocess.CompletedProcess(["git"], 0, "same\n", "")
            return subprocess.CompletedProcess(["git"], 1, "", "Not possible to fast-forward")

        with patch.object(studio_update, "_git", side_effect=fake_git):
            with self.assertRaisesRegex(RuntimeError, "fast-forward"):
                studio_update.update_from_github(lambda: None)


if __name__ == "__main__":
    unittest.main()

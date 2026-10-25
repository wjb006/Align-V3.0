"""Safety checks for local GitHub release dispatch."""
import subprocess
import unittest
from unittest.mock import patch

import studio_deploy


class StudioDeployTests(unittest.TestCase):
    def test_release_accepts_a_branch_and_rejects_unsafe_refs(self):
        self.assertEqual(
            studio_deploy.validate_release("  codex/align-v3-rebuild  ", "production"),
            ("codex/align-v3-rebuild", "production"),
        )
        for ref in ("../main", "main..backup", "main//release", "topic.lock", "https://example.com"):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                studio_deploy.validate_release(ref, "production")

    def test_release_target_is_allowlisted(self):
        with self.assertRaisesRegex(ValueError, "Only the configured production"):
            studio_deploy.validate_release("main", "staging")

    def test_dispatch_uses_github_cli_without_a_shell(self):
        successful = subprocess.CompletedProcess(["gh"], 0, "queued", "")
        with (
            patch.object(studio_deploy, "availability", return_value={"available": True}),
            patch.object(studio_deploy, "_gh_path", return_value="gh.exe"),
            patch.object(studio_deploy, "_run", return_value=successful) as run,
        ):
            result = studio_deploy.dispatch_release("main", "production")
        self.assertTrue(result["ok"])
        self.assertEqual(result["ref"], "main")
        args = run.call_args.args[0]
        self.assertEqual(args[0:3], ["gh.exe", "workflow", "run"])
        self.assertIn("--ref", args)
        self.assertEqual(args[args.index("--ref") + 1], studio_deploy.DEFAULT_REF)
        self.assertIn("source_ref=main", args)
        self.assertIn("target=production", args)

    def test_dispatch_reports_github_errors(self):
        failed = subprocess.CompletedProcess(["gh"], 1, "", "workflow not found")
        with (
            patch.object(studio_deploy, "availability", return_value={"available": True}),
            patch.object(studio_deploy, "_gh_path", return_value="gh.exe"),
            patch.object(studio_deploy, "_run", return_value=failed),
            self.assertRaisesRegex(RuntimeError, "workflow not found"),
        ):
            studio_deploy.dispatch_release("main", "production")


if __name__ == "__main__":
    unittest.main()

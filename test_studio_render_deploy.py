"""Tests for the secret-handling and target checks in Render releases."""
import unittest

import studio_render_deploy as deploy


class StudioRenderDeployTests(unittest.TestCase):
    def setUp(self):
        self.environ = {
            "RENDER_API_KEY": "test-only",
            "ALIGN_RENDER_SERVICE_ID": "srv-Ab12Cd34",
            "TESTED_SHA": "a" * 40,
        }

    def test_deploys_only_the_expected_service_and_checks_health(self):
        responses = iter([
            (200, {
                "name": "align-v3",
                "repo": "https://github.com/wjb006/Align-V3.0.git",
            }),
            (201, {"id": "dep-Ab12"}),
            (200, {"status": "live", "commit": {"id": "a" * 40}}),
        ])
        requests = []
        checks = []

        def request_json(path, api_key, method="GET", payload=None):
            requests.append((path, api_key, method, payload))
            return next(responses)

        result = deploy.run_deployment(
            self.environ,
            request_json=request_json,
            health_check=lambda: checks.append(True),
            sleep=lambda _: self.fail("A live deployment should not sleep."),
            clock=lambda: 0,
        )
        self.assertEqual(result["status"], "live")
        self.assertEqual(result["commit_id"], "a" * 40)
        self.assertEqual(checks, [True])
        self.assertEqual(requests[1][3], {"commitId": "a" * 40})

    def test_wrong_render_service_is_rejected_before_deploy(self):
        called = []

        def request_json(*args, **kwargs):
            called.append(args[0])
            return 200, {"name": "another-service", "repo": deploy.EXPECTED_REPOSITORY}

        with self.assertRaisesRegex(RuntimeError, "not named align-v3"):
            deploy.run_deployment(self.environ, request_json=request_json)
        self.assertEqual(len(called), 1)

    def test_wrong_repository_is_rejected_before_deploy(self):
        def request_json(*args, **kwargs):
            return 200, {"name": "align-v3", "repo": "https://github.com/another/repo"}

        with self.assertRaisesRegex(RuntimeError, "not connected"):
            deploy.run_deployment(self.environ, request_json=request_json)

    def test_invalid_service_id_or_untested_commit_is_rejected(self):
        for key, value in (("ALIGN_RENDER_SERVICE_ID", "srv-bad/value"), ("TESTED_SHA", "main")):
            with self.subTest(key=key):
                invalid = dict(self.environ, **{key: value})
                with self.assertRaises(RuntimeError):
                    deploy.run_deployment(invalid, request_json=lambda *args, **kwargs: self.fail("API called"))


if __name__ == "__main__":
    unittest.main()

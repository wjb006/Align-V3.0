"""The PC Management Studio must identify its trusted local Owner session."""
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

import admin_api


class OwnerSessionStatusTests(unittest.TestCase):
    def request(self, *, beta=False, authenticated=True, local=False, password=""):
        handler = Mock()
        handler.path = "/api/admin/status"
        handler.is_admin.return_value = authenticated
        handler.is_local_studio_request.return_value = local
        app = SimpleNamespace(BETA_MODE=beta, ADMIN_PASSWORD=password)
        self.assertTrue(admin_api.handle(handler, app, "GET"))
        handler.send_json.assert_called_once()
        status, payload = handler.send_json.call_args.args
        self.assertEqual(status, 200)
        return payload

    def test_installed_pc_reports_local_owner_session(self):
        result = self.request(local=True)
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["role"], "Owner")
        self.assertTrue(result["local_studio"])
        self.assertFalse(result["beta"])

    def test_non_local_admin_is_not_misidentified_as_pc_owner(self):
        result = self.request(authenticated=True, local=False, password="configured")
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["role"], "Owner")
        self.assertFalse(result["local_studio"])

    def test_hosted_owner_account_remains_authenticated_as_owner(self):
        result = self.request(beta=True, authenticated=True, local=False)
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["role"], "Owner")
        self.assertFalse(result["local_studio"])
        self.assertTrue(result["beta"])

    def test_unauthenticated_session_is_not_owner(self):
        result = self.request(authenticated=False, local=False, password="configured")
        self.assertFalse(result["authenticated"])
        self.assertEqual(result["role"], "Sign-in required")
        self.assertFalse(result["local_studio"])


if __name__ == "__main__":
    unittest.main()

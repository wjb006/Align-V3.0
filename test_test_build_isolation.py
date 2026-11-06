"""Guardrails for the isolated Windows test package."""
import unittest
from pathlib import Path


class TestBuildIsolationTests(unittest.TestCase):
    def test_frozen_test_entrypoint_is_separate_from_normal_user_data(self):
        hook = Path("desktop/pyi_rth_test_appcode.py").read_text(encoding="utf-8")
        self.assertIn('"Align-Test"', hook)
        self.assertIn('"8011"', hook)
        self.assertIn('"test/align-v3-readiness"', hook)
        self.assertIn('os.environ["ALIGN_LEGACY_DATABASES"] = ""', hook)
        self.assertIn('os.environ["ALIGN_DATA_DIR"]', hook)

    def test_test_installer_does_not_use_the_normal_programme_or_data_path(self):
        installer = Path("installer/windows/Install-Align-Test.ps1").read_text(encoding="utf-8")
        self.assertIn("Programs\\Align V3.0 Test", installer)
        self.assertIn("Align-Test", installer)
        self.assertNotIn("Programs\\Align Management Studio", installer)
        self.assertNotIn("Remove-Item", installer)

    def test_test_build_uses_its_own_executable_name(self):
        spec = Path("desktop/align.spec").read_text(encoding="utf-8")
        build = Path("desktop/build_test_windows.ps1").read_text(encoding="utf-8")
        self.assertIn('APP_NAME = "Align V3.0 Test" if TEST_BUILD else "Align"', spec)
        self.assertIn('$env:ALIGN_TEST_BUILD = "1"', build)


if __name__ == "__main__":
    unittest.main()

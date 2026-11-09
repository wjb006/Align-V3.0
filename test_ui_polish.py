"""Lock the Align UI polish: readable tokens, tap targets, and install/error feedback."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rel_luminance(hex_color):
    value = hex_color.lstrip("#")
    channels = [int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground, background):
    lighter, darker = sorted((rel_luminance(foreground), rel_luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class UiPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = (ROOT / "static/styles.css").read_text(encoding="utf-8")
        cls.app = (ROOT / "static/app.js").read_text(encoding="utf-8")
        cls.index = (ROOT / "static/index.html").read_text(encoding="utf-8")
        cls.worker = (ROOT / "static/service-worker.js").read_text(encoding="utf-8")
        cls.travel = (ROOT / "static/travel-assets.js").read_text(encoding="utf-8")
        cls.server = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.section_guide = (ROOT / "static/section-guide.js").read_text(encoding="utf-8")
        cls.migration = (ROOT / "migrations/158_section_guides.sql").read_text(encoding="utf-8")
        cls.owner_admin = (ROOT / "static/beta-admin.js").read_text(encoding="utf-8")
        cls.studio = (ROOT / "static/management-studio.html").read_text(encoding="utf-8")

    def token(self, name):
        match = re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", self.css)
        self.assertIsNotNone(match, name)
        return match.group(1)

    def test_text_tokens_meet_wcag_aa(self):
        canvas = self.token("canvas")
        surface = self.token("surface")
        self.assertGreaterEqual(contrast(self.token("muted"), canvas), 4.5)
        self.assertGreaterEqual(contrast(self.token("nav-ink"), surface), 4.5)
        self.assertGreaterEqual(contrast(self.token("ink"), canvas), 7)

    def test_tap_targets_and_shell_use_tokens(self):
        self.assertIn("--tap: 44px", self.css)
        self.assertIn("--shell: 720px", self.css)
        self.assertIn("--shell: 960px", self.css)
        self.assertIn("min-height: var(--tap)", self.css)
        self.assertIn("width: min(100%, var(--shell))", self.css)
        self.assertNotIn("white-space: nowrap; max-width: calc(100vw - 32px)", self.css)
        self.assertIn("#toast[data-tone=\"error\"]", self.css)
        self.assertIn("--edit-background: #061326 !important", self.css)

    def test_install_navigation_and_validation_feedback(self):
        self.assertIn('class="skip-link"', self.index)
        self.assertIn("header-install", self.index)
        self.assertRegex(self.index, r">\s*Install\s*<")
        self.assertNotIn("⇧", self.index)
        self.assertIn("function installPanel()", self.app)
        self.assertIn("data-action=\"prompt-install\"", self.app)
        self.assertIn("function showFormError(", self.app)
        self.assertIn("form.checkValidity()", self.app)
        self.assertIn("addEventListener('invalid'", self.app)
        self.assertIn("loading-state", self.app)
        self.assertIn("async function promptAlignInstall()", self.app)
        self.assertIn("f.checkValidity()", self.travel)
        self.assertIn("message.classList.add('form-error')", self.travel)
        self.assertIn('id="travel-message"', self.travel)

    def test_offline_cache_version_matches_the_shell(self):
        self.assertIn("158-v90", self.index)
        self.assertIn("`${BUILD_VERSION}-v90`", self.app)
        self.assertIn("`${BUILD}-v90`", self.worker)
        self.assertIn("/visual-theme.css?v=158-v90", self.index)
        self.assertIn("align-v13-shell-${ASSET_VERSION}", self.worker)
        self.assertNotIn("157-v21", self.index)

    def test_build_158_server_and_client_versions_match(self):
        self.assertIn("const BUILD_VERSION = 158;", self.app)
        self.assertIn("BUILD_VERSION = 158", self.server)
        self.assertIn("const BUILD = 158;", self.worker)
        self.assertIn("158-v90", self.index)
        self.assertIn("/section-guide.js?v=158-v90", self.index)

    def test_local_owner_screen_explains_hosted_only_features(self):
        self.assertIn("/beta-admin.js?v=158-v72", self.studio)
        self.assertIn("Not available in this local test installation.", self.owner_admin)
        self.assertIn("does not indicate a fault with Build 158 or your Microsoft account.", self.owner_admin)
        self.assertIn("https://getalign.co.uk/studio", self.owner_admin)

    def test_section_guides_are_included_in_build_158(self):
        self.assertIn("function openSectionGuide(", self.section_guide)
        self.assertIn("function openEventGuide(", self.section_guide)
        self.assertIn("CREATE TABLE IF NOT EXISTS saved_places", self.migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS planner_labels", self.migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS section_defaults", self.migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS organiser_event_details", self.migration)


if __name__ == "__main__":
    unittest.main()

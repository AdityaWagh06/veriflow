"""
Automated browser tests for authentication and account journeys.
"""

from __future__ import annotations

import unittest

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.browser_detector import detect_browser_environment
from skills.veriflow.scripts.browser_journeys import (
    launch_browser_context,
    test_auth_invalid_login,
    test_auth_nonexistent_account,
    test_auth_password_toggle,
    test_auth_registration_duplicate,
    test_auth_valid_login,
)


class TestBrowserAuthenticationJourneys(unittest.TestCase):
    """Verify real browser interaction with authentication flows."""

    @classmethod
    def setUpClass(cls):
        cls.env = detect_browser_environment(probe_launch=False)
        if not cls.env.playwright_installed or not cls.env.available_channels:
            raise unittest.SkipTest(f"Browser automation not available: {cls.env.reason}")

        cls.server = DemoServer(port=0)
        cls.base_url = cls.server.start()

        from playwright.sync_api import sync_playwright

        cls._pw_context = sync_playwright()
        cls.pw = cls._pw_context.start()
        cls.browser, cls.context = launch_browser_context(cls.pw)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser") and cls.browser:
            cls.browser.close()
        if hasattr(cls, "_pw_context") and cls._pw_context:
            cls.pw.stop()
        if hasattr(cls, "server") and cls.server:
            cls.server.stop()

    def setUp(self):
        self.page = self.context.new_page()

    def tearDown(self):
        self.page.close()

    def test_valid_login_journey(self):
        result = test_auth_valid_login(self.page, self.base_url)
        self.assertEqual(result.status, "PASS")
        self.assertIn("/dashboard", result.url)

    def test_invalid_login_journey(self):
        result = test_auth_invalid_login(self.page, self.base_url)
        self.assertEqual(result.status, "PASS")

    def test_nonexistent_account_journey(self):
        result = test_auth_nonexistent_account(self.page, self.base_url)
        self.assertEqual(result.status, "PASS")

    def test_password_visibility_toggle(self):
        result = test_auth_password_toggle(self.page, self.base_url)
        self.assertEqual(result.status, "PASS")

    def test_duplicate_registration_journey(self):
        result = test_auth_registration_duplicate(self.page, self.base_url)
        self.assertEqual(result.status, "PASS")


if __name__ == "__main__":
    unittest.main()

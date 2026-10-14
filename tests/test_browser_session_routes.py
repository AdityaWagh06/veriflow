"""
Automated browser tests for route guards and session lifecycle.
"""

from __future__ import annotations

import unittest

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.browser_detector import detect_browser_environment
from skills.veriflow.scripts.browser_journeys import (
    launch_browser_context,
    test_logout_invalidates_session,
    test_route_guard_unauthenticated,
    test_session_persistence_after_refresh,
)


class TestBrowserSessionAndRoutes(unittest.TestCase):
    """Verify route guard enforcement, session persistence, and logout invalidation."""

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
        self.context.clear_cookies()
        self.page = self.context.new_page()

    def tearDown(self):
        self.page.close()

    def test_unauthenticated_route_guard_redirect(self):
        result = test_route_guard_unauthenticated(self.page, self.base_url)
        self.assertEqual(result.status, "PASS")
        self.assertIn("/login", result.url)

    def test_session_persistence_across_refresh(self):
        result = test_session_persistence_after_refresh(self.page, self.base_url)
        self.assertEqual(result.status, "PASS")
        self.assertIn("/dashboard", result.url)

    def test_logout_invalidates_session(self):
        result = test_logout_invalidates_session(self.page, self.base_url)
        self.assertEqual(result.status, "PASS")


if __name__ == "__main__":
    unittest.main()

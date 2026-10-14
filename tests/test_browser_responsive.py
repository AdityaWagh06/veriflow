"""
Automated browser tests for responsive viewports and layout overflow.
"""

from __future__ import annotations

import unittest

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.browser_detector import detect_browser_environment
from skills.veriflow.scripts.browser_journeys import (
    launch_browser_context,
    test_responsive_desktop_viewport,
    test_responsive_mobile_viewport,
)


class TestBrowserResponsiveJourneys(unittest.TestCase):
    """Verify viewport layout reflow and horizontal overflow detection."""

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

    def test_mobile_viewport_without_overflow(self):
        result = test_responsive_mobile_viewport(self.page, self.base_url)
        self.assertEqual(result.status, "PASS")

    def test_desktop_viewport_layout(self):
        result = test_responsive_desktop_viewport(self.page, self.base_url)
        self.assertEqual(result.status, "PASS")


if __name__ == "__main__":
    unittest.main()

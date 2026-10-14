"""
Automated browser tests for console errors, unhandled exceptions, and network failure collection.
"""

from __future__ import annotations

import unittest

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.browser_detector import detect_browser_environment
from skills.veriflow.scripts.browser_journeys import (
    launch_browser_context,
    test_console_error_collection,
    test_network_failure_collection,
)


class TestBrowserNetworkAndConsole(unittest.TestCase):
    """Verify detection of JavaScript console errors and HTTP network request failures."""

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

    def test_clean_page_has_zero_console_errors(self):
        result = test_console_error_collection(self.page, self.base_url)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(len(result.console_messages), 0)

    def test_page_with_injected_js_error_fails(self):
        result = test_console_error_collection(self.page, self.base_url, fault="runtime_error")
        self.assertEqual(result.status, "FAIL")
        self.assertIn("Simulated JS error", result.evidence)

    def test_clean_network_requests_pass(self):
        result = test_network_failure_collection(self.page, self.base_url, request_faulty_endpoint=False)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(len(result.network_failures), 0)

    def test_failed_500_network_request_fails(self):
        result = test_network_failure_collection(self.page, self.base_url, request_faulty_endpoint=True)
        self.assertEqual(result.status, "FAIL")
        self.assertGreaterEqual(len(result.network_failures), 1)
        self.assertEqual(result.network_failures[0].status, 500)


if __name__ == "__main__":
    unittest.main()

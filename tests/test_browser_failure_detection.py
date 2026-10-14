"""
Tests validating that browser test journeys detect deliberately broken behaviors accurately.

Confirms that:
- Broken redirect fails while clean redirect passes.
- Broken route guard fails while clean route guard passes.
- Injected runtime JavaScript error fails while clean page passes.
- 500 network error fails while clean API passes.
"""

from __future__ import annotations

import unittest

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.browser_detector import detect_browser_environment
from skills.veriflow.scripts.browser_journeys import (
    launch_browser_context,
    test_auth_valid_login,
    test_console_error_collection,
    test_network_failure_collection,
    test_route_guard_unauthenticated,
)


class TestBrowserFailureDetection(unittest.TestCase):
    """Verify that tests fail genuinely on broken fixtures and pass on clean fixtures."""

    @classmethod
    def setUpClass(cls):
        cls.env = detect_browser_environment(probe_launch=False)
        if not cls.env.playwright_installed or not cls.env.available_channels:
            raise unittest.SkipTest(f"Browser automation not available: {cls.env.reason}")

        # Start a clean server and a faulty server
        cls.clean_server = DemoServer(port=0)
        cls.clean_url = cls.clean_server.start()

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
        if hasattr(cls, "clean_server") and cls.clean_server:
            cls.clean_server.stop()

    def setUp(self):
        self.context.clear_cookies()
        self.page = self.context.new_page()

    def tearDown(self):
        self.page.close()

    def test_broken_redirect_fails_while_clean_passes(self):
        fault_server = DemoServer(port=0, fault="faulty_redirect")
        fault_url = fault_server.start()
        try:
            p1 = self.context.new_page()
            broken_result = test_auth_valid_login(p1, fault_url)
            p1.close()
            self.assertEqual(broken_result.status, "FAIL")
            self.assertIn("Expected navigation to /dashboard", broken_result.error_message)
        finally:
            fault_server.stop()

        self.context.clear_cookies()
        p2 = self.context.new_page()
        clean_result = test_auth_valid_login(p2, self.clean_url)
        p2.close()
        self.assertEqual(clean_result.status, "PASS")

    def test_broken_auth_guard_fails_while_clean_passes(self):
        fault_server = DemoServer(port=0, fault="broken_auth_guard")
        fault_url = fault_server.start()
        try:
            self.context.clear_cookies()
            p1 = self.context.new_page()
            broken_result = test_route_guard_unauthenticated(p1, fault_url)
            p1.close()
            self.assertEqual(broken_result.status, "FAIL")
            self.assertIn("did not reject unauthenticated access", broken_result.error_message)
        finally:
            fault_server.stop()

        self.context.clear_cookies()
        p2 = self.context.new_page()
        clean_result = test_route_guard_unauthenticated(p2, self.clean_url)
        p2.close()
        self.assertEqual(clean_result.status, "PASS")

    def test_injected_js_runtime_error_fails_while_clean_passes(self):
        # 1. Broken fixture
        broken_result = test_console_error_collection(self.page, self.clean_url, fault="runtime_error")
        self.assertEqual(broken_result.status, "FAIL")
        self.assertIn("Simulated JS error", broken_result.evidence)

        # 2. Clean fixture
        clean_result = test_console_error_collection(self.page, self.clean_url, fault="")
        self.assertEqual(clean_result.status, "PASS")

    def test_failed_network_request_fails_while_clean_passes(self):
        # 1. Broken request
        broken_result = test_network_failure_collection(self.page, self.clean_url, request_faulty_endpoint=True)
        self.assertEqual(broken_result.status, "FAIL")

        # 2. Clean request
        clean_result = test_network_failure_collection(self.page, self.clean_url, request_faulty_endpoint=False)
        self.assertEqual(clean_result.status, "PASS")


if __name__ == "__main__":
    unittest.main()

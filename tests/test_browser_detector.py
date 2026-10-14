"""
Unit tests for Veriflow browser automation tool availability detector.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from skills.veriflow.scripts.browser_detector import (
    BrowserEnvironment,
    detect_browser_environment,
)


class TestBrowserDetector(unittest.TestCase):
    """Test browser tool availability detection logic."""

    def test_environment_dataclass_serialization(self):
        env = BrowserEnvironment(
            playwright_installed=True,
            playwright_version="1.40.0",
            available_channels=["chrome", "msedge"],
            default_channel="chrome",
            status="AVAILABLE",
            reason="Ready",
            remediation=None,
        )
        data = env.to_dict()
        self.assertTrue(data["playwright_installed"])
        self.assertEqual(data["status"], "AVAILABLE")
        self.assertEqual(data["available_channels"], ["chrome", "msedge"])
        self.assertEqual(data["default_channel"], "chrome")

    @patch("skills.veriflow.scripts.browser_detector.importlib.util.find_spec", return_value=None)
    def test_missing_playwright_reports_blocked(self, mock_find_spec):
        env = detect_browser_environment(probe_launch=False)
        self.assertFalse(env.playwright_installed)
        self.assertEqual(env.status, "BLOCKED")
        self.assertIn("not installed", env.reason)
        self.assertIsNotNone(env.remediation)
        self.assertIn("pip install playwright", env.remediation)

    def test_real_environment_detection_non_probing(self):
        env = detect_browser_environment(probe_launch=False)
        self.assertIsInstance(env.playwright_installed, bool)
        self.assertIn(env.status, ["AVAILABLE", "BLOCKED"])
        self.assertIsInstance(env.available_channels, list)

    @patch("skills.veriflow.scripts.browser_detector.importlib.util.find_spec")
    @patch("skills.veriflow.scripts.browser_detector.shutil.which")
    def test_system_browser_detection_without_launch(self, mock_which, mock_find_spec):
        mock_find_spec.return_value = True
        mock_which.side_effect = lambda cmd: "/usr/bin/google-chrome" if "chrome" in cmd else None

        env = detect_browser_environment(probe_launch=False)
        self.assertTrue(env.playwright_installed)
        self.assertIn("chrome", env.available_channels)
        self.assertEqual(env.default_channel, "chrome")
        self.assertEqual(env.status, "AVAILABLE")


if __name__ == "__main__":
    unittest.main()

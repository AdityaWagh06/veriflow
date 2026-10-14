"""
Unit and CLI invocation tests for standalone browser runner CLI.
"""

import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.veriflow.scripts.browser_detector import BrowserEnvironment, detect_browser_environment

# Load run-browser-tests.py dynamically since filename has hyphens
SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "skills"
    / "veriflow"
    / "scripts"
    / "run-browser-tests.py"
).resolve()

spec = importlib.util.spec_from_file_location("run_browser_tests_module", SCRIPT_PATH)
run_browser_tests_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run_browser_tests_module
spec.loader.exec_module(run_browser_tests_module)

run_browser_verification = run_browser_tests_module.run_browser_verification


class TestBrowserRunnerCLI(unittest.TestCase):
    """Test CLI modes, argument parsing, preview mode, and execution output."""

    @classmethod
    def setUpClass(cls):
        cls.env = detect_browser_environment(probe_launch=False)

    def test_preview_mode_returns_zero_and_shows_notice(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_browser_verification(execute=False, as_json=False)

        output = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Veriflow Browser Verification — Preview Mode", output)
        self.assertIn("Pass --execute to launch browser and run journeys", output)

    def test_preview_mode_json_output(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_browser_verification(execute=False, as_json=True)

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["mode"], "preview")
        self.assertIn("browser_environment", data)
        self.assertGreaterEqual(data["total_journeys"], 15)

    def test_filter_by_journey_category(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_browser_verification(execute=False, journey_filter="auth", as_json=True)

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        for j in data["journeys"]:
            self.assertEqual(j["category"], "AUTH")

    @patch.object(run_browser_tests_module, "detect_browser_environment")
    def test_blocked_environment_returns_code_2(self, mock_detect):
        mock_detect.return_value = BrowserEnvironment(
            playwright_installed=False,
            status="BLOCKED",
            reason="Playwright package missing",
            remediation="pip install playwright",
        )

        err_buf = io.StringIO()
        with patch("sys.stderr", err_buf):
            code = run_browser_verification(execute=True, as_json=False)

        self.assertEqual(code, 2)
        err_out = err_buf.getvalue()
        self.assertIn("[BLOCKED]", err_out)
        self.assertIn("pip install playwright", err_out)

    def test_execute_against_demo_server(self):
        if not self.env.playwright_installed or not self.env.available_channels:
            raise unittest.SkipTest(f"Browser automation not available: {self.env.reason}")

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            # Run a small journey subset (auth)
            code = run_browser_verification(execute=True, journey_filter="auth", as_json=True)

        self.assertEqual(code, 0)
        report = json.loads(buf.getvalue())
        self.assertIn("summary", report)
        self.assertGreater(report["summary"]["PASS"], 0)
        self.assertEqual(report["summary"]["FAIL"], 0)


if __name__ == "__main__":
    unittest.main()

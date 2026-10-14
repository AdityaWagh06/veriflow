"""
Unit tests validating the reproducible browser demo example runner (examples/browser-demo/run-demo.py).
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from skills.veriflow.scripts.browser_detector import BrowserEnvironment, detect_browser_environment

# Load run-demo.py dynamically
DEMO_PATH = (
    Path(__file__).parent.parent
    / "examples"
    / "browser-demo"
    / "run-demo.py"
).resolve()

spec = importlib.util.spec_from_file_location("demo_runner_module", DEMO_PATH)
demo_runner_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = demo_runner_module
spec.loader.exec_module(demo_runner_module)

run_demo = demo_runner_module.run_demo


class TestBrowserDemoExample(unittest.TestCase):
    """Test demo runner preview, fault injection handling, and execution."""

    @classmethod
    def setUpClass(cls):
        cls.env = detect_browser_environment(probe_launch=False)

    def test_demo_preview_mode_text(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_demo(preview=True, as_json=False)

        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("Veriflow Browser Demo — Preview Mode", out)
        self.assertIn("Remove --preview to execute browser journeys", out)

    def test_demo_preview_mode_json(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_demo(preview=True, as_json=True)

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["mode"], "preview")
        self.assertGreaterEqual(data["total_journeys"], 15)

    @patch.object(demo_runner_module, "detect_browser_environment")
    def test_demo_blocked_environment(self, mock_detect):
        mock_detect.return_value = BrowserEnvironment(
            playwright_installed=False,
            status="BLOCKED",
            reason="Playwright missing",
            remediation="pip install playwright",
        )

        err_buf = io.StringIO()
        with patch("sys.stderr", err_buf):
            code = run_demo(preview=False, as_json=False)

        self.assertEqual(code, 2)
        err = err_buf.getvalue()
        self.assertIn("[BLOCKED]", err)

    def test_demo_clean_execution_subset(self):
        if not self.env.playwright_installed or not self.env.available_channels:
            raise unittest.SkipTest(f"Browser automation not available: {self.env.reason}")

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_demo(preview=False, journey_filter="auth", as_json=True)

        self.assertEqual(code, 0)
        report = json.loads(buf.getvalue())
        self.assertEqual(report["summary"]["FAIL"], 0)
        self.assertGreater(report["summary"]["PASS"], 0)


if __name__ == "__main__":
    unittest.main()

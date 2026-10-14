"""
Unit tests for browser check discovery and execution integration in run-checks.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "skills"
    / "veriflow"
    / "scripts"
    / "run-checks.py"
).resolve()

spec = importlib.util.spec_from_file_location("run_checks_module", SCRIPT_PATH)
run_checks_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_checks_module)
discover_checks = run_checks_module.discover_checks


class TestBrowserRunChecksIntegration(unittest.TestCase):
    """Test browser check discovery in run-checks.py."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_no_browser_check_in_empty_project(self):
        result = discover_checks(self.root, execute=False)
        check_names = [c["name"] for c in result["discovered_checks"]]
        self.assertNotIn("browser", check_names)

    def test_discover_browser_check_when_test_file_present(self):
        tests_dir = self.root / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_browser_sample.py").write_text("# browser test file", encoding="utf-8")

        result = discover_checks(self.root, execute=False)
        check_names = [c["name"] for c in result["discovered_checks"]]
        self.assertIn("browser", check_names)

        browser_check = next(c for c in result["discovered_checks"] if c["name"] == "browser")
        self.assertEqual(browser_check["ecosystem"], "browser")
        self.assertFalse(browser_check["executed"])
        self.assertEqual(browser_check["status"], "proposed")

    def test_filter_by_browser_check(self):
        tests_dir = self.root / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_browser_auth.py").write_text("# browser test", encoding="utf-8")

        result = discover_checks(self.root, execute=False, check_name="browser")
        self.assertEqual(len(result["discovered_checks"]), 1)
        self.assertEqual(result["discovered_checks"][0]["name"], "browser")

    @patch.object(run_checks_module, "_load_browser_detector")
    def test_browser_check_blocked_when_tool_missing(self, mock_load):
        from skills.veriflow.scripts.browser_detector import BrowserEnvironment

        mock_load.return_value = lambda probe_launch=False: BrowserEnvironment(
            playwright_installed=False,
            status="BLOCKED",
            reason="Playwright not installed",
            remediation="pip install playwright",
        )

        tests_dir = self.root / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_browser_login.py").write_text("# browser test", encoding="utf-8")

        result = discover_checks(self.root, execute=False)
        browser_check = next(c for c in result["discovered_checks"] if c["name"] == "browser")
        self.assertEqual(browser_check["resolution_source"], "not_found")
        self.assertTrue(any("BLOCKED" in lim for lim in result["limitations"]))


if __name__ == "__main__":
    unittest.main()

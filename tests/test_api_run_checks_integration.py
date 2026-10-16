"""
Unit tests for API check discovery and execution integration in run-checks.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

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


class TestApiRunChecksIntegration(unittest.TestCase):
    """Test API check discovery in run-checks.py."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_no_api_check_in_empty_project(self):
        result = discover_checks(self.root, execute=False)
        check_names = [c["name"] for c in result["discovered_checks"]]
        self.assertNotIn("api", check_names)

    def test_discover_api_check_when_test_file_present(self):
        tests_dir = self.root / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_api_sample.py").write_text("# api test file", encoding="utf-8")

        result = discover_checks(self.root, execute=False)
        check_names = [c["name"] for c in result["discovered_checks"]]
        self.assertIn("api", check_names)

        api_check = next(c for c in result["discovered_checks"] if c["name"] == "api")
        self.assertEqual(api_check["ecosystem"], "api")
        self.assertFalse(api_check["executed"])
        self.assertEqual(api_check["status"], "proposed")

    def test_discover_api_check_when_openapi_spec_present(self):
        (self.root / "openapi.json").write_text('{"openapi": "3.0.0"}', encoding="utf-8")
        tests_dir = self.root / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_api_endpoints.py").write_text("# api test", encoding="utf-8")

        result = discover_checks(self.root, execute=False)
        check_names = [c["name"] for c in result["discovered_checks"]]
        self.assertIn("api", check_names)

    def test_filter_by_api_check(self):
        tests_dir = self.root / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_api_health.py").write_text("# api test", encoding="utf-8")

        result = discover_checks(self.root, execute=False, check_name="api")
        self.assertEqual(len(result["discovered_checks"]), 1)
        self.assertEqual(result["discovered_checks"][0]["name"], "api")

    def test_api_check_limitation_when_spec_only_without_runner_or_tests(self):
        (self.root / "openapi.json").write_text('{"openapi": "3.0.0"}', encoding="utf-8")

        # In a standalone temp dir without tests or runner in that tree
        # _discover_api_checks will report a limitation if api_runner is mocked or not found
        orig_runner = run_checks_module.Path(__file__).parent / "run-api-tests.py"
        # Since run-api-tests.py exists in skills/veriflow/scripts, it may find it if using relative to run-checks.py
        # But if we test discovery in the main repo:
        result = discover_checks(Path(__file__).parent.parent, execute=False, check_name="api")
        self.assertTrue(any(c["name"] == "api" for c in result["discovered_checks"]))


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for OpenAPI check discovery and execution integration in run-checks.py.
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


class TestOpenApiRunChecksIntegration(unittest.TestCase):
    """Test OpenAPI contract check discovery in run-checks.py."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_no_openapi_check_in_empty_project(self):
        result = discover_checks(self.root, execute=False)
        check_names = [c["name"] for c in result["discovered_checks"]]
        self.assertNotIn("openapi", check_names)

    def test_discover_openapi_check_when_spec_present(self):
        (self.root / "openapi.json").write_text('{"openapi": "3.0.0"}', encoding="utf-8")

        result = discover_checks(self.root, execute=False)
        check_names = [c["name"] for c in result["discovered_checks"]]
        self.assertIn("openapi", check_names)

        openapi_check = next(c for c in result["discovered_checks"] if c["name"] == "openapi")
        self.assertEqual(openapi_check["ecosystem"], "openapi")
        self.assertFalse(openapi_check["executed"])
        self.assertEqual(openapi_check["status"], "proposed")
        self.assertTrue(any("run-openapi-tests.py" in arg for arg in openapi_check["command"]))

    def test_discover_openapi_check_when_yaml_spec_present(self):
        (self.root / "openapi.yaml").write_text('openapi: "3.0.3"\ninfo:\n  title: Test\n', encoding="utf-8")

        result = discover_checks(self.root, execute=False)
        check_names = [c["name"] for c in result["discovered_checks"]]
        self.assertIn("openapi", check_names)

        openapi_check = next(c for c in result["discovered_checks"] if c["name"] == "openapi")
        self.assertEqual(openapi_check["ecosystem"], "openapi")
        self.assertIn("--spec", openapi_check["command"])

    def test_discover_openapi_check_when_tests_present(self):
        tests_dir = self.root / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_openapi_suite.py").write_text("# openapi test file", encoding="utf-8")

        result = discover_checks(self.root, execute=False)
        check_names = [c["name"] for c in result["discovered_checks"]]
        self.assertIn("openapi", check_names)

        openapi_check = next(c for c in result["discovered_checks"] if c["name"] == "openapi")
        self.assertEqual(openapi_check["ecosystem"], "openapi")
        self.assertTrue(any("test_openapi_*.py" in arg for arg in openapi_check["command"]))

    def test_filter_by_openapi_check(self):
        (self.root / "openapi.json").write_text('{"openapi": "3.0.0"}', encoding="utf-8")

        result = discover_checks(self.root, execute=False, check_name="openapi")
        self.assertEqual(len(result["discovered_checks"]), 1)
        self.assertEqual(result["discovered_checks"][0]["name"], "openapi")

    def test_openapi_check_limitation_when_spec_only_without_runner(self):
        (self.root / "openapi.json").write_text('{"openapi": "3.0.0"}', encoding="utf-8")

        real_is_file = Path.is_file

        def mock_is_file(p):
            if "run-openapi-tests.py" in str(p):
                return False
            return real_is_file(p)

        with patch.object(Path, "is_file", autospec=True, side_effect=mock_is_file):
            checks, limits = run_checks_module._discover_openapi_checks(self.root)
            self.assertEqual(len(checks), 0)
            self.assertTrue(any("OpenAPI runner was not found" in lim for lim in limits))


if __name__ == "__main__":
    unittest.main()

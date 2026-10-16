"""
Unit tests for the standalone API test runner CLI (run-api-tests.py).
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "skills"
    / "veriflow"
    / "scripts"
    / "run-api-tests.py"
).resolve()

spec = importlib.util.spec_from_file_location("run_api_tests_module", SCRIPT_PATH)
run_api_tests_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run_api_tests_module
spec.loader.exec_module(run_api_tests_module)

run_api_verification = run_api_tests_module.run_api_verification


class TestApiRunnerCLI(unittest.TestCase):
    """Test CLI preview mode, execution mode, filtering, JSON reporting, and safety blocks."""

    def test_preview_mode_text_output(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_api_verification(execute=False, as_json=False)

        output = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Veriflow API Verification — Preview Mode", output)
        self.assertIn("Pass --execute to execute live HTTP verification checks", output)
        self.assertIn("[API-001]", output)
        self.assertIn("[RESL-006]", output)

    def test_preview_mode_json_output(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_api_verification(execute=False, as_json=True)

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["mode"], "preview")
        self.assertGreaterEqual(data["total_checks"], 10)
        self.assertIn("checks", data)

    def test_filter_by_category(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_api_verification(execute=False, check_filter="AUTH", as_json=True)

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        for c in data["checks"]:
            self.assertEqual(c["category"], "AUTH")

    def test_unsafe_external_target_blocked(self):
        err_buf = io.StringIO()
        with patch("sys.stderr", err_buf):
            code = run_api_verification(
                target_url="https://api.external-cloud.com",
                execute=True,
                allow_external=False,
                as_json=False,
            )

        self.assertEqual(code, 2)
        err_out = err_buf.getvalue()
        self.assertIn("[BLOCKED]", err_out)
        self.assertIn("not a local/loopback address", err_out)

    def test_unsafe_external_target_blocked_json(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_api_verification(
                target_url="https://api.production-payment.com",
                execute=True,
                allow_external=False,
                as_json=True,
            )

        self.assertEqual(code, 2)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "BLOCKED")
        self.assertIn("Target safety validation failed", data["error"])

    def test_live_execution_against_local_demo(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            # Run clean execution filtered to RESL-006 (fast single check)
            code = run_api_verification(
                execute=True,
                check_filter="RESL-006",
                as_json=True,
            )

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["summary"]["PASS"], 1)
        self.assertEqual(data["summary"]["FAIL"], 0)


if __name__ == "__main__":
    unittest.main()

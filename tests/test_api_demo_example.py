"""
Unit tests validating the reproducible API demo example runner (examples/api-demo/run-demo.py).
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

# Load run-demo.py dynamically
DEMO_PATH = (
    Path(__file__).parent.parent
    / "examples"
    / "api-demo"
    / "run-demo.py"
).resolve()

spec = importlib.util.spec_from_file_location("api_demo_runner_module", DEMO_PATH)
api_demo_runner_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api_demo_runner_module
spec.loader.exec_module(api_demo_runner_module)

run_demo = api_demo_runner_module.run_demo


class TestApiDemoExample(unittest.TestCase):
    """Test API demo runner preview, fault injection, and execution."""

    def test_demo_preview_mode_text(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_demo(preview=True, as_json=False)

        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("Veriflow API Verification Demo — Preview Mode", out)
        self.assertIn("Run without --preview to execute", out)

    def test_demo_preview_mode_json(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_demo(preview=True, as_json=True)

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["mode"], "preview")
        self.assertGreaterEqual(data["total_checks"], 10)

    def test_demo_clean_execution(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_demo(preview=False, as_json=True)

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["summary"]["FAIL"], 0)
        self.assertGreater(data["summary"]["PASS"], 0)

    def test_demo_fault_execution_schema(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_demo(fault="schema", preview=False, as_json=True)

        self.assertEqual(code, 1)
        data = json.loads(buf.getvalue())
        self.assertGreater(data["summary"]["FAIL"], 0)

    def test_demo_filtered_check(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_demo(check_filter="API-001", preview=False, as_json=True)

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["total_tests"], 1)
        self.assertEqual(data["results"][0]["test_id"], "API-001")

    def test_demo_invalid_fault(self):
        buf = io.StringIO()
        with patch("sys.stderr", buf):
            code = run_demo(fault="nonexistent_fault", preview=False, as_json=False)

        self.assertEqual(code, 1)
        self.assertIn("Unknown fault", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

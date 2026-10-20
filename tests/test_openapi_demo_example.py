"""
Unit tests validating the reproducible OpenAPI demo example runner (examples/openapi-demo/run-demo.py).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

from tests.optional_deps import require_pyyaml

DEMO_RUNNER = Path(__file__).parent.parent / "examples" / "openapi-demo" / "run-demo.py"


class TestOpenApiDemoExample(unittest.TestCase):
    """Test OpenAPI demo runner preview, spec validation, clean execution, and fault injection."""

    def test_demo_preview_mode(self):
        proc = subprocess.run(
            [sys.executable, str(DEMO_RUNNER), "--preview"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Preview Mode", proc.stdout)
        self.assertIn("Pass --execute to execute live contract verification checks", proc.stdout)

    def test_demo_validate_spec_only_json(self):
        proc = subprocess.run(
            [sys.executable, str(DEMO_RUNNER), "--validate-spec-only"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Specification: openapi.json", proc.stdout)
        self.assertIn("[PASS] Document structure and schema references are valid", proc.stdout)

    def test_demo_validate_spec_only_yaml(self):
        require_pyyaml()

        proc = subprocess.run(
            [sys.executable, str(DEMO_RUNNER), "--yaml", "--validate-spec-only"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Specification: openapi.yaml", proc.stdout)
        self.assertIn("[PASS] Document structure and schema references are valid", proc.stdout)

    def test_demo_clean_execution_json(self):
        proc = subprocess.run(
            [sys.executable, str(DEMO_RUNNER), "--format", "json"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        self.assertEqual(report["summary"]["FAIL"], 0)
        self.assertEqual(report["summary"]["BLOCKED"], 0)
        self.assertGreaterEqual(report["summary"]["PASS"], 8)

    def test_demo_clean_execution_yaml(self):
        require_pyyaml()

        proc = subprocess.run(
            [sys.executable, str(DEMO_RUNNER), "--yaml", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        self.assertEqual(report["summary"]["FAIL"], 0)
        self.assertGreaterEqual(report["summary"]["PASS"], 8)

    def test_demo_fault_missing_field(self):
        proc = subprocess.run(
            [sys.executable, str(DEMO_RUNNER), "--fault", "missing_field", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertGreaterEqual(report["summary"]["FAIL"], 1)

    def test_demo_fault_wrong_status(self):
        proc = subprocess.run(
            [sys.executable, str(DEMO_RUNNER), "--fault", "wrong_status", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertGreaterEqual(report["summary"]["FAIL"], 1)

    def test_demo_fault_wrong_content_type(self):
        proc = subprocess.run(
            [sys.executable, str(DEMO_RUNNER), "--fault", "wrong_content_type", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertGreaterEqual(report["summary"]["FAIL"], 1)

    def test_demo_fault_invalid_type(self):
        proc = subprocess.run(
            [sys.executable, str(DEMO_RUNNER), "--fault", "invalid_type", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertGreaterEqual(report["summary"]["FAIL"], 1)

    def test_demo_filtered_operation(self):
        proc = subprocess.run(
            [sys.executable, str(DEMO_RUNNER), "--check", "getHealth", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        self.assertEqual(report["total_tests"], 1)
        self.assertEqual(report["results"][0]["test_id"], "RESL-006")


if __name__ == "__main__":
    unittest.main()

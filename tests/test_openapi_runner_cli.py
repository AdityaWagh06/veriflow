"""
Unit tests for the standalone OpenAPI runner CLI (skills/veriflow/scripts/run-openapi-tests.py).
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from skills.veriflow.demo_app.server import DemoServer

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "skills"
    / "veriflow"
    / "scripts"
    / "run-openapi-tests.py"
).resolve()

spec = importlib.util.spec_from_file_location("run_openapi_tests_module", SCRIPT_PATH)
run_openapi_tests_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run_openapi_tests_module
spec.loader.exec_module(run_openapi_tests_module)

run_openapi_cli = run_openapi_tests_module.run_openapi_cli


class TestOpenApiRunnerCli(unittest.TestCase):
    """Test CLI argument handling, preview mode, static validation, and execution."""

    @classmethod
    def setUpClass(cls):
        cls.server = DemoServer(port=0)
        cls.base_url = cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        self.spec_file = self.base_path / "openapi.json"
        self.spec_data = {
            "openapi": "3.0.3",
            "info": {"title": "CLI Test API", "version": "1.0.0"},
            "paths": {
                "/api/health": {
                    "get": {
                        "operationId": "getHealth",
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["status"],
                                            "properties": {"status": {"type": "string"}},
                                        }
                                    }
                                },
                            }
                        },
                    }
                }
            },
        }
        self.spec_file.write_text(json.dumps(self.spec_data), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cli_preview_mode_text(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_openapi_cli(spec_path=str(self.spec_file), execute=False, as_json=False)

        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("Veriflow OpenAPI Contract Verification — Preview Mode", out)
        self.assertIn("Pass --execute to execute live contract verification checks", out)

    def test_cli_preview_mode_json(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_openapi_cli(spec_path=str(self.spec_file), execute=False, as_json=True)

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["mode"], "preview")
        self.assertEqual(data["openapi_version"], "3.0.3")
        self.assertGreaterEqual(data["total_checks"], 2)

    def test_cli_validate_spec_only(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_openapi_cli(spec_path=str(self.spec_file), validate_spec_only=True, as_json=False)

        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("Veriflow OpenAPI Specification Validation", out)
        self.assertIn("[PASS] Document structure and schema references are valid", out)

    def test_cli_missing_spec_file(self):
        err_buf = io.StringIO()
        with patch("sys.stderr", err_buf):
            code = run_openapi_cli(spec_path=str(self.base_path / "nonexistent.json"), execute=False)

        self.assertEqual(code, 1)
        self.assertIn("does not exist", err_buf.getvalue())

    def test_cli_live_execution_against_fixture(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_openapi_cli(
                spec_path=str(self.spec_file),
                target_url=self.base_url,
                execute=True,
                as_json=True,
            )

        self.assertEqual(code, 0)
        report = json.loads(buf.getvalue())
        self.assertEqual(report["summary"]["FAIL"], 0)
        self.assertGreaterEqual(report["summary"]["PASS"], 2)

    def test_cli_filter_checks(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = run_openapi_cli(
                spec_path=str(self.spec_file),
                execute=False,
                check_filter="health",
                as_json=True,
            )

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["total_checks"], 1)
        self.assertIn("health", data["checks"][0]["check_id"].lower())


if __name__ == "__main__":
    unittest.main()

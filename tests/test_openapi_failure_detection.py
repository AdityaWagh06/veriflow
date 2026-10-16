"""
Unit tests validating that Veriflow's OpenAPI contract verification engine detects real defects
when fault injection modes are active, and passes cleanly when the compliant fixture is active.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

from skills.veriflow.scripts.openapi_checks import (
    generate_contract_checks,
    run_openapi_contract_verification,
)
from skills.veriflow.scripts.openapi_loader import (
    OpenApiSpecError,
    load_openapi_spec,
)

DEMO_DIR = Path(__file__).parent.parent / "examples" / "openapi-demo"
SPEC_JSON = DEMO_DIR / "openapi.json"
SPEC_YAML = DEMO_DIR / "openapi.yaml"
SPECS_DIR = DEMO_DIR / "specs"

server_script = DEMO_DIR / "server.py"
spec_srv = importlib.util.spec_from_file_location("openapi_demo_server_module", server_script)
mod_srv = importlib.util.module_from_spec(spec_srv)
spec_srv.loader.exec_module(mod_srv)
OpenApiDemoServer = mod_srv.OpenApiDemoServer


class TestOpenApiFailureDetection(unittest.TestCase):
    """Test contract violation detection across all fault injection modes."""

    def test_clean_fixture_passes_all_contract_checks(self):
        spec = load_openapi_spec(SPEC_JSON)
        server = OpenApiDemoServer(port=0, fault="")
        url = server.start()
        try:
            report = run_openapi_contract_verification(spec, base_url=url, execute=True)
            counts = report.summary_counts()
            self.assertEqual(counts["FAIL"], 0)
            self.assertEqual(counts["BLOCKED"], 0)
            self.assertGreaterEqual(counts["PASS"], 8)
        finally:
            server.stop()

    def test_clean_yaml_fixture_passes_all_contract_checks(self):
        spec = load_openapi_spec(SPEC_YAML)
        server = OpenApiDemoServer(port=0, fault="")
        url = server.start()
        try:
            report = run_openapi_contract_verification(spec, base_url=url, execute=True)
            counts = report.summary_counts()
            self.assertEqual(counts["FAIL"], 0)
            self.assertGreaterEqual(counts["PASS"], 8)
        finally:
            server.stop()

    def test_missing_field_fault_fails_contract_check(self):
        spec = load_openapi_spec(SPEC_JSON)
        server = OpenApiDemoServer(port=0, fault="missing_field")
        url = server.start()
        try:
            report = run_openapi_contract_verification(spec, base_url=url, execute=True)
            items_res = next((r for r in report.results if "OA-GET-/api/items" in r.name), None)
            self.assertIsNotNone(items_res)
            self.assertEqual(items_res.status, "FAIL")
            self.assertIn("price", str(items_res.error_message).lower())
            self.assertIn("missing", str(items_res.error_message).lower())
        finally:
            server.stop()

    def test_wrong_status_fault_fails_contract_check(self):
        spec = load_openapi_spec(SPEC_JSON)
        server = OpenApiDemoServer(port=0, fault="wrong_status")
        url = server.start()
        try:
            report = run_openapi_contract_verification(spec, base_url=url, execute=True)
            health_res = next((r for r in report.results if "OA-GET-/api/health" in r.name), None)
            self.assertIsNotNone(health_res)
            self.assertEqual(health_res.status, "FAIL")
            self.assertTrue(
                "500" in str(health_res.error_message)
                or "status" in str(health_res.error_message).lower()
            )
        finally:
            server.stop()

    def test_wrong_content_type_fault_fails_contract_check(self):
        spec = load_openapi_spec(SPEC_JSON)
        server = OpenApiDemoServer(port=0, fault="wrong_content_type")
        url = server.start()
        try:
            report = run_openapi_contract_verification(spec, base_url=url, execute=True)
            health_res = next((r for r in report.results if "OA-GET-/api/health" in r.name), None)
            self.assertIsNotNone(health_res)
            self.assertEqual(health_res.status, "FAIL")
            self.assertIn("content-type", str(health_res.error_message).lower())
            self.assertIn("text/plain", str(health_res.error_message).lower())
        finally:
            server.stop()

    def test_invalid_type_fault_fails_contract_check(self):
        spec = load_openapi_spec(SPEC_JSON)
        server = OpenApiDemoServer(port=0, fault="invalid_type")
        url = server.start()
        try:
            report = run_openapi_contract_verification(spec, base_url=url, execute=True)
            profile_res = next((r for r in report.results if "OA-GET-/api/profile" in r.name and "AUTH" not in r.name), None)
            self.assertIsNotNone(profile_res)
            self.assertEqual(profile_res.status, "FAIL")
            self.assertIn("type mismatch", str(profile_res.error_message).lower())
            self.assertIn("boolean", str(profile_res.error_message).lower())
        finally:
            server.stop()

    def test_broken_spec_missing_fields_fails_validation(self):
        with self.assertRaises(OpenApiSpecError) as ctx:
            load_openapi_spec(SPECS_DIR / "missing_fields.json")
        self.assertIn("info", str(ctx.exception).lower())

    def test_broken_spec_invalid_version_fails_validation(self):
        with self.assertRaises(OpenApiSpecError) as ctx:
            load_openapi_spec(SPECS_DIR / "invalid_version.json")
        self.assertIn("unsupported", str(ctx.exception).lower())

    def test_broken_spec_unresolved_ref_fails_resolution(self):
        spec = load_openapi_spec(SPECS_DIR / "unresolved_ref.json")
        checks = generate_contract_checks(spec)
        from skills.veriflow.scripts.openapi_checks import execute_contract_check
        res = execute_contract_check(checks[0], base_url="", spec=spec, execute=True)
        self.assertEqual(res.status, "FAIL")
        self.assertIn("unresolved reference", str(res.error_message).lower())

    def test_broken_spec_path_traversal_fails_resolution(self):
        spec = load_openapi_spec(SPECS_DIR / "path_traversal_ref.json")
        checks = generate_contract_checks(spec)
        from skills.veriflow.scripts.openapi_checks import execute_contract_check
        res = execute_contract_check(checks[0], base_url="", spec=spec, execute=True)
        self.assertEqual(res.status, "FAIL")
        self.assertIn("path traversal", str(res.error_message).lower())


if __name__ == "__main__":
    unittest.main()

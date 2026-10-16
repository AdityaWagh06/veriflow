"""
Unit tests validating that Veriflow's API verification routines detect real defects
when fault injection modes are active, and pass when the clean fixture is active.
"""

from __future__ import annotations

import unittest

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.api_checks import (
    check_api_auth_required,
    check_api_health,
    check_api_input_validation,
    check_api_role_authorization_denial,
    check_api_schema_contract,
    check_api_server_error_defense,
)


class TestApiFailureDetection(unittest.TestCase):
    """Test defect detection across all fault modes."""

    def test_clean_fixture_passes_core_checks(self):
        server = DemoServer(port=0)
        url = server.start()
        try:
            self.assertEqual(check_api_health(url).status, "PASS")
            self.assertEqual(check_api_schema_contract(url).status, "PASS")
            self.assertEqual(check_api_input_validation(url).status, "PASS")
            self.assertEqual(check_api_auth_required(url).status, "PASS")
            self.assertEqual(check_api_role_authorization_denial(url).status, "PASS")
            self.assertEqual(check_api_server_error_defense(url).status, "PASS")
        finally:
            server.stop()

    def test_schema_fault_fails_contract_check(self):
        server = DemoServer(port=0, fault="fault_api_schema")
        url = server.start()
        try:
            result = check_api_schema_contract(url)
            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.test_id, "API-001")
            self.assertIn("price", str(result.error_message).lower())
        finally:
            server.stop()

    def test_stacktrace_leak_fault_fails_defense_check(self):
        server = DemoServer(port=0, fault="fault_api_stacktrace")
        url = server.start()
        try:
            result = check_api_server_error_defense(url)
            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.test_id, "SEC-009")
            self.assertTrue(
                "traceback" in (result.error_message or "").lower()
                or "leak" in (result.error_message or "").lower()
            )
        finally:
            server.stop()

    def test_auth_bypass_fault_fails_auth_check(self):
        server = DemoServer(port=0, fault="fault_api_auth_bypass")
        url = server.start()
        try:
            result = check_api_auth_required(url)
            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.test_id, "AUTH-001")
            self.assertIn("401", (result.error_message or "").lower())
            self.assertIn("200", (result.error_message or "").lower())
        finally:
            server.stop()

    def test_role_bypass_fault_fails_role_authorization_check(self):
        server = DemoServer(port=0, fault="fault_api_role_bypass")
        url = server.start()
        try:
            result = check_api_role_authorization_denial(url)
            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.test_id, "ROLE-003")
            self.assertIn("403", (result.error_message or "").lower())
            self.assertIn("200", (result.error_message or "").lower())
        finally:
            server.stop()

    def test_missing_validation_fault_fails_input_validation_check(self):
        server = DemoServer(port=0, fault="fault_api_missing_validation")
        url = server.start()
        try:
            result = check_api_input_validation(url)
            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.test_id, "FORM-001")
            self.assertIn("400", (result.error_message or "").lower())
            self.assertIn("201", (result.error_message or "").lower())
        finally:
            server.stop()

    def test_unavailable_server_fails_health_check(self):
        result = check_api_health("http://127.0.0.1:59999", timeout=0.5)
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.test_id, "RESL-006")
        self.assertTrue(
            "timed out" in (result.error_message or "").lower()
            or "refused" in (result.error_message or "").lower()
            or "failed" in (result.error_message or "").lower()
            or "unavailable" in (result.error_message or "").lower()
        )


if __name__ == "__main__":
    unittest.main()

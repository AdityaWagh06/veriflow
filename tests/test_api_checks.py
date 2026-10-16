"""
Unit tests for all automated API verification routines in api_checks.py.
"""

from __future__ import annotations

import unittest

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.api_checks import (
    CHECK_FUNCTIONS,
    check_api_auth_required,
    check_api_client_error_formatting,
    check_api_crud_lifecycle,
    check_api_defensive_parsing,
    check_api_dependency_outage,
    check_api_health,
    check_api_http_methods,
    check_api_input_validation,
    check_api_rate_limiting,
    check_api_readiness,
    check_api_role_authorization_denial,
    check_api_schema_contract,
    check_api_server_error_defense,
    check_api_timeout_handling,
    get_api_checks_mapping,
    run_catalog_api_test,
)


class TestApiChecks(unittest.TestCase):
    """Test all API verification checks against clean DemoServer."""

    @classmethod
    def setUpClass(cls):
        cls.server = DemoServer(port=0)
        cls.base_url = cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_check_api_health(self):
        res = check_api_health(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "RESL-006")
        self.assertEqual(res.status_code, 200)

    def test_check_api_readiness(self):
        res = check_api_readiness(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "API-READY")
        self.assertEqual(res.status_code, 200)

    def test_check_api_schema_contract(self):
        res = check_api_schema_contract(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "API-001")
        self.assertEqual(res.status_code, 200)

    def test_check_api_client_error_formatting(self):
        res = check_api_client_error_formatting(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "API-002")
        self.assertEqual(res.status_code, 400)

    def test_check_api_input_validation(self):
        res = check_api_input_validation(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "FORM-001")
        self.assertEqual(res.status_code, 400)

    def test_check_api_auth_required(self):
        res = check_api_auth_required(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "AUTH-001")

    def test_check_api_role_authorization_denial(self):
        res = check_api_role_authorization_denial(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "ROLE-003")

    def test_check_api_server_error_defense(self):
        res = check_api_server_error_defense(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "SEC-009")
        self.assertEqual(res.status_code, 500)

    def test_check_api_defensive_parsing(self):
        res = check_api_defensive_parsing(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "API-006")

    def test_check_api_timeout_handling(self):
        res = check_api_timeout_handling(self.base_url, timeout=0.3)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "API-004")

    def test_check_api_dependency_outage(self):
        res = check_api_dependency_outage(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "API-008")

    def test_check_api_rate_limiting(self):
        res = check_api_rate_limiting(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "API-007")

    def test_check_api_crud_lifecycle(self):
        res = check_api_crud_lifecycle(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "DATA-001")

    def test_check_api_http_methods(self):
        res = check_api_http_methods(self.base_url)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.test_id, "API-METHOD")
        self.assertEqual(res.status_code, 405)

    def test_get_api_checks_mapping_count(self):
        mappings = get_api_checks_mapping()
        self.assertEqual(len(mappings), 14)
        for m in mappings:
            self.assertIn("catalog_id", m)
            self.assertIn("name", m)
            self.assertIn("category", m)
            self.assertIn("check_function", m)

    def test_run_catalog_api_test_unmapped(self):
        res = run_catalog_api_test("NONEXISTENT-999", self.base_url)
        self.assertEqual(res.status, "NOT_APPLICABLE")


if __name__ == "__main__":
    unittest.main()

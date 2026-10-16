"""
Unit tests validating deterministic API fault injection modes in DemoServer.
"""

from __future__ import annotations

import json
import unittest

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.api_safety import safe_http_request


class TestApiFaultServer(unittest.TestCase):
    """Test that DemoServer fault injection flags reliably produce defect conditions."""

    def test_fault_api_schema_drops_price(self):
        server = DemoServer(port=0, fault="fault_api_schema")
        url = server.start()
        try:
            resp = safe_http_request(f"{url}/api/items")
            self.assertEqual(resp.status, 200)
            items = resp.json()
            # In fault mode, price field is absent
            self.assertNotIn("price", items[0])
        finally:
            server.stop()

    def test_fault_api_stacktrace_leaks_traceback(self):
        server = DemoServer(port=0, fault="fault_api_stacktrace")
        url = server.start()
        try:
            resp = safe_http_request(f"{url}/api/faulty/crash")
            self.assertEqual(resp.status, 500)
            self.assertIn("Traceback (most recent call last)", resp.body_text)
            self.assertIn("Password=db_super_secret_123", resp.body_text)
        finally:
            server.stop()

    def test_fault_api_auth_bypass_allows_unauthenticated(self):
        server = DemoServer(port=0, fault="fault_api_auth_bypass")
        url = server.start()
        try:
            resp = safe_http_request(f"{url}/api/profile")
            # In fault mode, unauthenticated request returns 200 instead of 401
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.json()["username"], "bypassed_user")
        finally:
            server.stop()

    def test_fault_api_role_bypass_allows_non_admin(self):
        server = DemoServer(port=0, fault="fault_api_role_bypass")
        url = server.start()
        try:
            resp = safe_http_request(
                f"{url}/api/admin/metrics",
                headers={"Authorization": "Bearer token_user"},
            )
            # In fault mode, standard user gets 200 instead of 403
            self.assertEqual(resp.status, 200)
            self.assertIn("active_sessions", resp.json())
        finally:
            server.stop()

    def test_fault_api_missing_validation_accepts_negative_price(self):
        server = DemoServer(port=0, fault="fault_api_missing_validation")
        url = server.start()
        try:
            payload = json.dumps({"name": "Negative Price Item", "price": -99.0})
            resp = safe_http_request(
                f"{url}/api/items",
                method="POST",
                headers={"Content-Type": "application/json"},
                body=payload,
            )
            # In fault mode, accepts negative price with 201 instead of returning 400
            self.assertEqual(resp.status, 201)
            self.assertEqual(resp.json()["price"], -99.0)
        finally:
            server.stop()

    def test_fault_api_dependency_returns_503(self):
        server = DemoServer(port=0, fault="fault_api_dependency")
        url = server.start()
        try:
            resp = safe_http_request(f"{url}/api/dependency/status")
            self.assertEqual(resp.status, 503)
            self.assertEqual(resp.json()["code"], "DEPENDENCY_UNAVAILABLE")
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()

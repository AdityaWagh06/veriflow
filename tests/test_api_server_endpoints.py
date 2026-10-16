"""
Unit tests validating the expanded deterministic API endpoints on DemoServer.
"""

from __future__ import annotations

import json
import unittest

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.api_safety import safe_http_request


class TestApiServerEndpoints(unittest.TestCase):
    """Test clean API endpoints, status codes, schemas, and error responses."""

    @classmethod
    def setUpClass(cls):
        cls.server = DemoServer(port=0)
        cls.base_url = cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_health_and_ready_endpoints(self):
        for path in ("/api/health", "/api/ready"):
            with self.subTest(path=path):
                resp = safe_http_request(f"{self.base_url}{path}")
                self.assertEqual(resp.status, 200)
                self.assertTrue(resp.is_json)
                data = resp.json()
                self.assertEqual(data["status"], "ok")
                self.assertEqual(data["service"], "veriflow-demo-api")
                self.assertEqual(data["dependencies"]["database"], "connected")

    def test_get_items_schema(self):
        resp = safe_http_request(f"{self.base_url}/api/items")
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.is_json)
        items = resp.json()
        self.assertIsInstance(items, list)
        self.assertGreaterEqual(len(items), 2)
        item = items[0]
        self.assertIn("id", item)
        self.assertIn("name", item)
        self.assertIn("price", item)
        self.assertIn("category", item)

    def test_post_items_validation_and_creation(self):
        # 1. Valid creation
        payload = json.dumps({"name": "Test Gadget", "price": 25.50, "category": "Testing"})
        resp = safe_http_request(
            f"{self.base_url}/api/items",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=payload,
        )
        self.assertEqual(resp.status, 201)
        created = resp.json()
        self.assertEqual(created["name"], "Test Gadget")
        self.assertEqual(created["price"], 25.50)
        new_id = created["id"]

        # Verify get by ID
        get_resp = safe_http_request(f"{self.base_url}/api/items/{new_id}")
        self.assertEqual(get_resp.status, 200)
        self.assertEqual(get_resp.json()["name"], "Test Gadget")

        # 2. Invalid creation: missing name
        bad_payload = json.dumps({"price": 20.0})
        bad_resp = safe_http_request(
            f"{self.base_url}/api/items",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=bad_payload,
        )
        self.assertEqual(bad_resp.status, 400)
        err_data = bad_resp.json()
        self.assertEqual(err_data["code"], "VALIDATION_ERROR")
        self.assertIn("name", [e["field"] for e in err_data.get("details", [])])

        # 3. Invalid creation: negative price
        neg_payload = json.dumps({"name": "Bad Price", "price": -5.0})
        neg_resp = safe_http_request(
            f"{self.base_url}/api/items",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=neg_payload,
        )
        self.assertEqual(neg_resp.status, 400)

    def test_delete_item_lifecycle(self):
        # Create disposable item
        payload = json.dumps({"name": "To Delete", "price": 9.99})
        resp = safe_http_request(
            f"{self.base_url}/api/items",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=payload,
        )
        self.assertEqual(resp.status, 201)
        item_id = resp.json()["id"]

        # Delete it
        del_resp = safe_http_request(f"{self.base_url}/api/items/{item_id}", method="DELETE")
        self.assertEqual(del_resp.status, 204)

        # Confirm 404
        get_resp = safe_http_request(f"{self.base_url}/api/items/{item_id}")
        self.assertEqual(get_resp.status, 404)

    def test_auth_profile_endpoint(self):
        # 1. Unauthenticated -> 401
        unauth = safe_http_request(f"{self.base_url}/api/profile")
        self.assertEqual(unauth.status, 401)
        self.assertEqual(unauth.json()["code"], "UNAUTHORIZED")

        # 2. Authenticated via Bearer token -> 200
        auth = safe_http_request(
            f"{self.base_url}/api/profile",
            headers={"Authorization": "Bearer token_user"},
        )
        self.assertEqual(auth.status, 200)
        self.assertEqual(auth.json()["username"], "alice")

    def test_role_admin_metrics_endpoint(self):
        # 1. Unauthenticated -> 401
        unauth = safe_http_request(f"{self.base_url}/api/admin/metrics")
        self.assertEqual(unauth.status, 401)

        # 2. Authenticated standard user -> 403 Forbidden
        user_auth = safe_http_request(
            f"{self.base_url}/api/admin/metrics",
            headers={"Authorization": "Bearer token_user"},
        )
        self.assertEqual(user_auth.status, 403)
        self.assertEqual(user_auth.json()["code"], "FORBIDDEN")

        # 3. Authenticated admin -> 200 OK
        admin_auth = safe_http_request(
            f"{self.base_url}/api/admin/metrics",
            headers={"Authorization": "Bearer token_admin"},
        )
        self.assertEqual(admin_auth.status, 200)
        self.assertIn("active_sessions", admin_auth.json())

    def test_clean_500_suppresses_stack_trace(self):
        resp = safe_http_request(f"{self.base_url}/api/faulty/crash")
        self.assertEqual(resp.status, 500)
        self.assertTrue(resp.is_json)
        self.assertNotIn("Traceback", resp.body_text)
        self.assertNotIn("Password", resp.body_text)

    def test_method_not_allowed(self):
        resp = safe_http_request(f"{self.base_url}/api/health", method="POST")
        self.assertEqual(resp.status, 405)
        self.assertEqual(resp.headers.get("allow"), "GET")


if __name__ == "__main__":
    unittest.main()

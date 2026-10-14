"""
Unit tests for the Veriflow deterministic demo web server fixture.
"""

from __future__ import annotations

import unittest
import urllib.request
import urllib.parse
from http import client

from skills.veriflow.demo_app.server import DemoServer


class TestDemoServer(unittest.TestCase):
    """Test standard HTTP responses, cookies, and route guards of demo app."""

    @classmethod
    def setUpClass(cls):
        cls.server = DemoServer(port=0)
        cls.base_url = cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_home_page_returns_200_and_html(self):
        req = urllib.request.Request(f"{self.base_url}/")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("Welcome to Veriflow Demo App", body)
            self.assertIn("VeriflowApp", body)

    def test_health_endpoint_returns_json(self):
        req = urllib.request.Request(f"{self.base_url}/api/health")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "application/json; charset=utf-8")
            body = resp.read().decode("utf-8")
            self.assertIn('"status": "ok"', body)

    def test_dashboard_unauthenticated_redirects_to_login(self):
        # Prevent auto-redirect to inspect 302 Location header
        class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def http_error_302(self, req, fp, code, msg, headers):
                return fp

        opener = urllib.request.build_opener(NoRedirectHandler)
        resp = opener.open(f"{self.base_url}/dashboard")
        self.assertEqual(resp.code, 302)
        location = resp.headers.get("Location")
        self.assertIn("/login?returnUrl=%2Fdashboard", location)

    def test_login_valid_sets_cookie_and_redirects(self):
        class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def http_error_302(self, req, fp, code, msg, headers):
                return fp

        opener = urllib.request.build_opener(NoRedirectHandler)
        data = urllib.parse.urlencode({"username": "admin", "password": "secret123", "returnUrl": "/dashboard"}).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/login", data=data, method="POST")
        resp = opener.open(req)
        self.assertEqual(resp.code, 302)
        self.assertEqual(resp.headers.get("Location"), "/dashboard")
        set_cookie = resp.headers.get("Set-Cookie")
        self.assertIn("vf_session=admin", set_cookie)

    def test_login_invalid_redirects_with_error(self):
        class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def http_error_302(self, req, fp, code, msg, headers):
                return fp

        opener = urllib.request.build_opener(NoRedirectHandler)
        data = urllib.parse.urlencode({"username": "admin", "password": "wrongpassword"}).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/login", data=data, method="POST")
        resp = opener.open(req)
        self.assertEqual(resp.code, 302)
        self.assertIn("error=Invalid+username+or+password", resp.headers.get("Location"))

    def test_404_page(self):
        try:
            urllib.request.urlopen(f"{self.base_url}/nonexistent-route-404")
            self.fail("Expected HTTPError 404")
        except urllib.error.HTTPError as err:
            self.assertEqual(err.code, 404)
            body = err.read().decode("utf-8")
            self.assertIn("404 — Page Not Found", body)


class TestDemoServerFaultInjection(unittest.TestCase):
    """Test that fault simulation flags alter behavior deterministically."""

    def test_broken_auth_guard_allows_dashboard(self):
        fault_server = DemoServer(port=0, fault="broken_auth_guard")
        url = fault_server.start()
        try:
            req = urllib.request.Request(f"{url}/dashboard")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                body = resp.read().decode("utf-8")
                self.assertIn("Anonymous (Broken Guard)", body)
        finally:
            fault_server.stop()


if __name__ == "__main__":
    unittest.main()

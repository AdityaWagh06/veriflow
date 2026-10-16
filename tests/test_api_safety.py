"""
Unit tests for Veriflow API target safety and bounded request utilities.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from skills.veriflow.scripts.api_safety import (
    SafeHttpResponse,
    UnsafeTargetError,
    is_local_target,
    safe_http_request,
    validate_target_url,
)


class TestApiSafety(unittest.TestCase):
    """Test target validation, loopback restriction, and bounded requests."""

    def test_is_local_target_recognizes_local_addresses(self):
        self.assertTrue(is_local_target("http://localhost:3000"))
        self.assertTrue(is_local_target("http://127.0.0.1:8080/api"))
        self.assertTrue(is_local_target("http://[::1]:5000"))
        self.assertTrue(is_local_target("http://0.0.0.0:8000"))
        self.assertTrue(is_local_target("127.0.0.1"))
        self.assertTrue(is_local_target("localhost"))

    def test_is_local_target_rejects_external_hosts(self):
        self.assertFalse(is_local_target("http://example.com"))
        self.assertFalse(is_local_target("https://api.github.com"))
        self.assertFalse(is_local_target("http://8.8.8.8"))
        self.assertFalse(is_local_target("http://192.168.1.100"))
        self.assertFalse(is_local_target(""))

    def test_validate_target_url_accepts_valid_local_url(self):
        url = "http://localhost:8000/api/health"
        self.assertEqual(validate_target_url(url), url)

        ip_url = "http://127.0.0.1:5000/"
        self.assertEqual(validate_target_url(ip_url), ip_url)

    def test_validate_target_url_rejects_external_by_default(self):
        with self.assertRaises(UnsafeTargetError) as ctx:
            validate_target_url("https://api.external-saas.com/v1")
        self.assertIn("not a local/loopback address", str(ctx.exception))

    def test_validate_target_url_allow_external_flag(self):
        url = "https://api.example.com/v1"
        self.assertEqual(validate_target_url(url, allow_external=True), url)

    def test_validate_target_url_rejects_invalid_schemes(self):
        with self.assertRaises(UnsafeTargetError):
            validate_target_url("ftp://localhost:21")
        with self.assertRaises(UnsafeTargetError):
            validate_target_url("file:///etc/passwd")
        with self.assertRaises(UnsafeTargetError):
            validate_target_url("javascript:alert(1)")

    def test_validate_target_url_rejects_empty_or_non_string(self):
        with self.assertRaises(UnsafeTargetError):
            validate_target_url("")
        with self.assertRaises(UnsafeTargetError):
            validate_target_url(None)  # type: ignore

    def test_safe_http_response_properties(self):
        resp = SafeHttpResponse(
            status=200,
            headers={"content-type": "application/json; charset=utf-8"},
            body_text='{"status": "ok", "count": 3}',
        )
        self.assertTrue(resp.is_json)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["count"], 3)

    def test_safe_http_request_blocks_external_target(self):
        with self.assertRaises(UnsafeTargetError):
            safe_http_request("https://production-bank.com/api")


if __name__ == "__main__":
    unittest.main()

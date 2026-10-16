"""
Unit tests for Veriflow API result schema, redaction, and reporting.
"""

from __future__ import annotations

import unittest

from skills.veriflow.scripts.api_reporter import (
    ApiExecutionReport,
    ApiTestResult,
    redact_api_data,
    redact_headers,
)


class TestApiReporter(unittest.TestCase):
    """Test API result model, credential masking, and reporting."""

    def test_status_validation(self):
        # Valid status
        res = ApiTestResult(test_id="API-001", name="Schema Check", status="PASS")
        self.assertEqual(res.status, "PASS")

        # Invalid status raises ValueError
        with self.assertRaises(ValueError):
            ApiTestResult(test_id="API-001", name="Bad Status", status="SUCCEEDED")

    def test_credential_redaction_in_text(self):
        # Bearer token
        raw_auth = "Authorization: Bearer secret_jwt_token_12345"
        self.assertNotIn("secret_jwt_token_12345", redact_api_data(raw_auth))
        self.assertIn("Bearer [REDACTED]", redact_api_data(raw_auth))

        # Query param
        raw_query = "GET /api/data?api_key=secret9876&user=alice"
        redacted = redact_api_data(raw_query)
        self.assertNotIn("secret9876", redacted)
        self.assertIn("api_key=[REDACTED]", redacted)
        self.assertIn("user=alice", redacted)

        # JSON body sensitive fields
        raw_json = '{"username": "admin", "password": "supersecretpassword", "token": "xyz123"}'
        redacted_json = redact_api_data(raw_json)
        self.assertNotIn("supersecretpassword", redacted_json)
        self.assertNotIn("xyz123", redacted_json)
        self.assertIn('"password": "[REDACTED]"', redacted_json)
        self.assertIn('"token": "[REDACTED]"', redacted_json)

    def test_redact_headers(self):
        headers = {
            "Authorization": "Bearer topsecret",
            "Cookie": "vf_session=admin; session_id=abc",
            "Content-Type": "application/json",
            "X-Api-Key": "my-secret-key",
        }
        sanitized = redact_headers(headers)
        self.assertEqual(sanitized["Authorization"], "[REDACTED]")
        self.assertEqual(sanitized["Cookie"], "[REDACTED]")
        self.assertEqual(sanitized["X-Api-Key"], "[REDACTED]")
        self.assertEqual(sanitized["Content-Type"], "application/json")

    def test_report_summary_and_formatting(self):
        report = ApiExecutionReport(target_url="http://127.0.0.1:8000")
        report.add_result(ApiTestResult(test_id="API-001", name="Schema", status="PASS", status_code=200))
        report.add_result(ApiTestResult(test_id="API-002", name="Client Error", status="FAIL", status_code=500, error_message="Internal error"))
        report.add_result(ApiTestResult(test_id="API-007", name="Rate Limit", status="BLOCKED", remediation="Configure rate limiter"))

        counts = report.summary_counts()
        self.assertEqual(counts["PASS"], 1)
        self.assertEqual(counts["FAIL"], 1)
        self.assertEqual(counts["BLOCKED"], 1)
        self.assertEqual(counts["NOT_RUN"], 0)

        text = report.format_text()
        self.assertIn("Veriflow API & Integration Verification Report", text)
        self.assertIn("[  PASS  ] API-001", text)
        self.assertIn("[  FAIL  ] API-002", text)
        self.assertIn("[BLOCKED ] API-007", text)
        self.assertIn("PASS=1 | FAIL=1 | BLOCKED=1", text)

        as_dict = report.to_dict()
        self.assertEqual(as_dict["total_tests"], 3)
        self.assertEqual(len(as_dict["results"]), 3)


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for Veriflow browser test result schema and diagnostic reporter.
"""

from __future__ import annotations

import unittest

from skills.veriflow.scripts.browser_reporter import (
    BrowserConsoleEntry,
    BrowserExecutionReport,
    BrowserNetworkFailure,
    BrowserTestResult,
    redact_sensitive_data,
)


class TestBrowserReporter(unittest.TestCase):
    """Test browser result schema, redaction, and formatting."""

    def test_status_validation(self):
        # Valid status
        result = BrowserTestResult(
            test_id="AUTH-001",
            name="Valid login test",
            status="PASS",
            duration_ms=120.5,
        )
        self.assertEqual(result.status, "PASS")

        # Invalid status should raise ValueError
        with self.assertRaises(ValueError):
            BrowserTestResult(
                test_id="AUTH-001",
                name="Invalid status test",
                status="COMPLETED",  # Not in 7 valid statuses
            )

    def test_redact_sensitive_data(self):
        raw = "POST /api/login password=SuperSecret123&token=xyz789 Bearer eyJhbGciOiJIUzI1NiJ9"
        sanitized = redact_sensitive_data(raw)
        self.assertNotIn("SuperSecret123", sanitized)
        self.assertIn("password=[REDACTED]", sanitized)
        self.assertIn("token=[REDACTED]", sanitized)
        self.assertIn("Bearer [REDACTED]", sanitized)

    def test_console_and_network_entry_serialization(self):
        console = BrowserConsoleEntry(
            level="error",
            text="Uncaught TypeError: secret_token=12345 is undefined",
            location="app.js:42",
        )
        c_dict = console.to_dict()
        self.assertEqual(c_dict["level"], "error")
        self.assertNotIn("12345", c_dict["text"])
        self.assertIn("[REDACTED]", c_dict["text"])

        net = BrowserNetworkFailure(
            url="http://localhost:3000/api/auth?token=mysecret",
            method="POST",
            status=500,
            error_text="Internal Server Error: password=abc",
        )
        n_dict = net.to_dict()
        self.assertEqual(n_dict["status"], 500)
        self.assertNotIn("mysecret", n_dict["url"])
        self.assertNotIn("abc", n_dict["error_text"])

    def test_report_summary_and_formatting(self):
        report = BrowserExecutionReport(
            target_url="http://localhost:8080",
            browser_channel="chrome",
        )
        report.add_result(BrowserTestResult(test_id="AUTH-001", name="Login", status="PASS", duration_ms=45.0))
        report.add_result(BrowserTestResult(test_id="AUTH-002", name="Bad Login", status="PASS", duration_ms=30.0))
        report.add_result(BrowserTestResult(test_id="ROUTE-005", name="404 Page", status="FAIL", error_message="Wrong title"))
        report.add_result(BrowserTestResult(test_id="ROLE-001", name="Admin", status="BLOCKED", remediation="Admin credentials required"))

        counts = report.summary_counts()
        self.assertEqual(counts["PASS"], 2)
        self.assertEqual(counts["FAIL"], 1)
        self.assertEqual(counts["BLOCKED"], 1)
        self.assertEqual(counts["NOT_RUN"], 0)

        formatted = report.format_text()
        self.assertIn("Veriflow Browser Verification Report", formatted)
        self.assertIn("[  PASS  ] AUTH-001", formatted)
        self.assertIn("[  FAIL  ] ROUTE-005", formatted)
        self.assertIn("[BLOCKED ] ROLE-001", formatted)
        self.assertIn("PASS=2 | FAIL=1 | BLOCKED=1", formatted)


if __name__ == "__main__":
    unittest.main()

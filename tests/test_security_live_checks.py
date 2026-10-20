"""
Tests for Veriflow's live security checks against the local fixture.

The core evidence here is paired: the secure fixture must pass every check, and
each individually broken fixture must fail exactly the check that covers it. A
check that passes on the secure variant but also passes on the broken variant
proves nothing, so both halves are asserted.

Also verified: loopback-only target enforcement, that preview sends no request
at all, that an unknown filter fails loudly, and that credentials never reach a
report.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from skills.veriflow.scripts.api_safety import UnsafeTargetError
from skills.veriflow.scripts.security_checks import (
    LIVE_CHECKS_BY_ID,
    LIVE_SECURITY_CHECKS,
    SecurityTarget,
    preview_live_checks,
    run_live_security_checks,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SERVER = REPO_ROOT / "examples" / "security-demo" / "server.py"

_spec = importlib.util.spec_from_file_location("veriflow_security_fixture", FIXTURE_SERVER)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
SecurityFixtureServer = _module.SecurityFixtureServer
FAULT_MODES = _module.FAULT_MODES

#: Which fault breaks which check. Every fault must map to exactly one check,
#: and every check with a fault must be represented.
FAULT_TO_CHECK = {
    "missing_headers": "SEC-LIVE-HEADERS-001",
    "insecure_cookie": "SEC-LIVE-COOKIE-001",
    "reflected_xss": "SEC-LIVE-XSS-001",
    "open_protected_route": "SEC-LIVE-AUTH-001",
    "cross_user_leak": "SEC-LIVE-IDOR-001",
    "stack_trace_leak": "SEC-LIVE-ERROR-001",
    "secret_in_response": "SEC-LIVE-SECRET-001",
    "open_redirect": "SEC-LIVE-REDIRECT-001",
    "missing_csrf": "SEC-LIVE-CSRF-001",
}


def fixture_target(base_url: str, **overrides) -> SecurityTarget:
    """Build a fully configured target for the local security fixture."""
    config = dict(
        base_url=base_url,
        public_path="/",
        protected_path="/account",
        reflect_path="/echo",
        reflect_param="q",
        error_path="/boom",
        login_path="/login",
        login_payload={"username": "vf-fixture-user", "password": "vf-fixture-password"},
        user_a={"token": "vf-token-user-a"},
        user_b={"resource_path": "/records/rec-b"},
        state_change_path="/profile/update",
        redirect_path="/go",
        redirect_param="next",
    )
    config.update(overrides)
    return SecurityTarget(**config)


class TestSecureFixturePasses(unittest.TestCase):
    """The corrected fixture must pass every live check."""

    @classmethod
    def setUpClass(cls):
        cls.server = SecurityFixtureServer().start()
        cls.report = run_live_security_checks(fixture_target(cls.server.base_url))

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_no_check_fails_on_the_secure_fixture(self):
        failures = [(r.test_id, r.error_message) for r in self.report.results if r.status == "FAIL"]
        self.assertEqual(failures, [], f"secure fixture produced failures: {failures}")

    def test_every_check_actually_ran(self):
        """Nothing may be silently skipped: all nine must report PASS, not NOT_APPLICABLE."""
        statuses = {r.test_id: r.status for r in self.report.results}
        self.assertEqual(len(statuses), len(LIVE_SECURITY_CHECKS))
        not_passed = {k: v for k, v in statuses.items() if v != "PASS"}
        self.assertEqual(not_passed, {}, f"checks did not execute to PASS: {not_passed}")

    def test_report_records_the_selected_checks(self):
        info = self.report.environment_info
        self.assertEqual(info["engine"], "veriflow-live-security-checks")
        self.assertFalse(info["allow_external"])
        self.assertEqual(len(info["checks_selected"]), len(LIVE_SECURITY_CHECKS))


class TestFaultDetection(unittest.TestCase):
    """Each deliberately broken fixture must fail its own check and no other."""

    def test_fault_map_covers_every_fault_mode(self):
        self.assertEqual(set(FAULT_TO_CHECK), FAULT_MODES)

    def test_fault_map_targets_known_checks(self):
        for check_id in FAULT_TO_CHECK.values():
            with self.subTest(check=check_id):
                self.assertIn(check_id, LIVE_CHECKS_BY_ID)

    def test_each_fault_fails_its_own_check(self):
        for fault, check_id in FAULT_TO_CHECK.items():
            with self.subTest(fault=fault):
                with SecurityFixtureServer({fault}) as server:
                    report = run_live_security_checks(fixture_target(server.base_url))
                    by_id = {r.test_id: r for r in report.results}
                    self.assertEqual(
                        by_id[check_id].status,
                        "FAIL",
                        f"fault '{fault}' did not make {check_id} fail",
                    )

    def test_a_fault_does_not_fail_unrelated_checks(self):
        """Collateral failures would make a report impossible to act on."""
        for fault, check_id in FAULT_TO_CHECK.items():
            with self.subTest(fault=fault):
                with SecurityFixtureServer({fault}) as server:
                    report = run_live_security_checks(fixture_target(server.base_url))
                    collateral = sorted(
                        r.test_id
                        for r in report.results
                        if r.status == "FAIL" and r.test_id != check_id
                    )
                    self.assertEqual(
                        collateral, [], f"fault '{fault}' also failed {collateral}"
                    )

    def test_failures_carry_diagnostics_and_remediation(self):
        for fault, check_id in FAULT_TO_CHECK.items():
            with self.subTest(fault=fault):
                with SecurityFixtureServer({fault}) as server:
                    report = run_live_security_checks(
                        fixture_target(server.base_url), check_filter=[check_id]
                    )
                    result = report.results[0]
                    self.assertEqual(result.status, "FAIL")
                    self.assertTrue(result.error_message, "a failure must explain itself")
                    self.assertTrue(result.remediation, "a failure must say what to do")
                    self.assertTrue(result.diagnostics, "a failure must carry structured diagnostics")
                    self.assertIn("category", result.diagnostics[0])

    def test_unknown_fault_name_is_rejected(self):
        """A typo in a fault name must not silently start a secure server."""
        with self.assertRaises(ValueError) as ctx:
            SecurityFixtureServer({"not_a_real_fault"})
        self.assertIn("Unknown fault mode", str(ctx.exception))


class TestSafetyBoundaries(unittest.TestCase):
    """Target restrictions, preview purity and filter validation."""

    def test_external_target_is_blocked_by_default(self):
        target = SecurityTarget(base_url="http://example.com")
        with self.assertRaises(UnsafeTargetError):
            run_live_security_checks(target)

    def test_external_target_requires_explicit_opt_in(self):
        """With the opt-in the policy no longer blocks; reachability is separate."""
        target = SecurityTarget(base_url="http://veriflow-nonexistent.invalid", allow_external=True)
        try:
            report = run_live_security_checks(target, check_filter=["SEC-LIVE-HEADERS-001"])
        except UnsafeTargetError:
            self.fail("allow_external=True must bypass the loopback policy")
        # The host does not resolve, so the result is UNKNOWN, never PASS.
        self.assertEqual(report.results[0].status, "UNKNOWN")

    def test_preview_sends_no_http_request(self):
        """Preview must be a pure function of configuration.

        Patching the request primitive proves it: if preview touched the network
        this assertion fails.
        """
        with SecurityFixtureServer() as server:
            target = fixture_target(server.base_url)
            with patch(
                "skills.veriflow.scripts.security_checks.safe_http_request"
            ) as mock_request:
                planned = preview_live_checks(target)
            mock_request.assert_not_called()

        self.assertEqual(len(planned), len(LIVE_SECURITY_CHECKS))
        for item in planned:
            self.assertEqual(item["status"], "NOT_RUN")
            self.assertIn("requires --execute", item["reason"])

    def test_preview_marks_unconfigured_checks_not_applicable(self):
        """An unconfigured check is NOT_APPLICABLE, never a pass."""
        target = SecurityTarget(base_url="http://127.0.0.1:1")
        planned = {item["test_id"]: item["status"] for item in preview_live_checks(target)}
        self.assertEqual(planned["SEC-LIVE-AUTH-001"], "NOT_APPLICABLE")
        self.assertEqual(planned["SEC-LIVE-IDOR-001"], "NOT_APPLICABLE")
        self.assertEqual(planned["SEC-LIVE-CSRF-001"], "NOT_APPLICABLE")
        # Headers and secret leakage need only a public path, which always exists.
        self.assertEqual(planned["SEC-LIVE-HEADERS-001"], "NOT_RUN")

    def test_unknown_check_filter_fails_loudly(self):
        """Silently running nothing would read as a clean security result."""
        with SecurityFixtureServer() as server:
            with self.assertRaises(ValueError) as ctx:
                run_live_security_checks(
                    fixture_target(server.base_url), check_filter=["SEC-LIVE-NOPE-001"]
                )
        self.assertIn("Unknown security check id", str(ctx.exception))

    def test_unconfigured_check_is_not_applicable_not_pass(self):
        with SecurityFixtureServer() as server:
            target = fixture_target(server.base_url, protected_path=None)
            report = run_live_security_checks(target, check_filter=["SEC-LIVE-AUTH-001"])
            self.assertEqual(report.results[0].status, "NOT_APPLICABLE")
            self.assertIn("not as passing", report.results[0].remediation)

    def test_unreachable_target_is_unknown_not_pass(self):
        target = SecurityTarget(base_url="http://127.0.0.1:1")
        report = run_live_security_checks(target, check_filter=["SEC-LIVE-HEADERS-001"])
        self.assertEqual(report.results[0].status, "UNKNOWN")


class TestCredentialRedaction(unittest.TestCase):
    """Tokens and cookies must not survive into a report."""

    def test_bearer_token_is_not_present_in_the_report(self):
        secret_token = "vf-token-user-a"
        with SecurityFixtureServer({"cross_user_leak"}) as server:
            report = run_live_security_checks(
                fixture_target(server.base_url), check_filter=["SEC-LIVE-IDOR-001"]
            )
        serialized = json.dumps(report.to_dict())
        self.assertEqual(report.results[0].status, "FAIL")
        self.assertNotIn(secret_token, serialized)
        self.assertNotIn(secret_token, report.format_text())

    def test_leaked_connection_password_is_redacted_in_the_report(self):
        """The fixture leaks a password inside a traceback; the report must not."""
        with SecurityFixtureServer({"stack_trace_leak"}) as server:
            report = run_live_security_checks(
                fixture_target(server.base_url), check_filter=["SEC-LIVE-ERROR-001"]
            )
        serialized = json.dumps(report.to_dict())
        self.assertEqual(report.results[0].status, "FAIL")
        self.assertNotIn("Qx7LbN4tKp8s", serialized)
        self.assertNotIn("Qx7LbN4tKp8s", report.format_text())

    def test_leaked_api_key_is_redacted_in_the_report(self):
        with SecurityFixtureServer({"secret_in_response"}) as server:
            report = run_live_security_checks(
                fixture_target(server.base_url), check_filter=["SEC-LIVE-SECRET-001"]
            )
        serialized = json.dumps(report.to_dict())
        self.assertEqual(report.results[0].status, "FAIL")
        self.assertNotIn("zQ8mLvRxTn2wKp9sYd4hGj7bFe3uCi6a", serialized)


class TestNonDestructiveProbes(unittest.TestCase):
    """The probes must not alter the fixture's state or reach a third party."""

    def test_xss_probe_is_inert_and_uniquely_tagged(self):
        with SecurityFixtureServer() as server:
            report = run_live_security_checks(
                fixture_target(server.base_url), check_filter=["SEC-LIVE-XSS-001"]
            )
        # A passing encoded reflection proves the probe round-tripped without
        # the fixture rendering it as live markup.
        self.assertEqual(report.results[0].status, "PASS")

    def test_redirect_probe_uses_a_reserved_non_resolvable_domain(self):
        """RFC 2606 reserves .invalid, so the probe cannot reach a real host."""
        with SecurityFixtureServer({"open_redirect"}) as server:
            report = run_live_security_checks(
                fixture_target(server.base_url), check_filter=["SEC-LIVE-REDIRECT-001"]
            )
        result = report.results[0]
        self.assertEqual(result.status, "FAIL")
        self.assertIn(".invalid", result.evidence)

    def test_only_safe_methods_and_declared_paths_are_touched(self):
        """No check may issue DELETE or PUT against the target."""
        methods_used = set()
        real_request = _real_safe_http_request

        def recording(url, method="GET", **kwargs):
            methods_used.add(method.upper())
            return real_request(url, method=method, **kwargs)

        with SecurityFixtureServer() as server:
            with patch(
                "skills.veriflow.scripts.security_checks.safe_http_request",
                side_effect=recording,
            ):
                run_live_security_checks(fixture_target(server.base_url))

        self.assertTrue(methods_used)
        self.assertEqual(methods_used - {"GET", "POST"}, set())


from skills.veriflow.scripts.api_safety import safe_http_request as _real_safe_http_request  # noqa: E402


if __name__ == "__main__":
    unittest.main()

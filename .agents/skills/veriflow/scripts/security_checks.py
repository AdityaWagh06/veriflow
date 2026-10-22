#!/usr/bin/env python3
"""
Veriflow Live Security Checks (Phase 5).

Runtime security verification against a running service. These checks answer the
questions static analysis cannot: what headers does the service actually send,
are session cookies actually flagged, does an unauthenticated request actually
get refused, and does one user's token actually fail to read another user's
record.

Safety model (inherited from ``api_safety``, not reimplemented):

- **Loopback only by default.** A target must resolve to 127.0.0.0/8 or ::1.
  Reaching anything else requires an explicit ``allow_external`` opt-in.
- **Non-destructive by default.** Checks issue reads and benign, clearly
  labelled probes. Nothing deletes, nothing floods, nothing brute-forces.
- **Synthetic identities only.** Cross-user isolation uses two fictional
  accounts supplied by the caller; no real credential is ever required.
- **Probes are inert.** The reflected-input probe uses a unique benign marker
  and asserts on *encoding*, so it proves output handling without delivering a
  working payload.
- **Credentials never reach a report.** Every result passes through the
  ``api_reporter`` redaction layer.

These checks reduce common, detectable defects. They are not a penetration test
and cannot establish that a service is secure.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Package path first so the engine and the test suite share one module object
# (and therefore one exception class); flat path for direct script execution.
try:  # noqa: E402  - sys.path is prepared above
    from skills.veriflow.scripts.api_reporter import (
        ApiExecutionReport,
        ApiTestResult,
        redact_api_data,
        redact_headers,
    )
    from skills.veriflow.scripts.api_safety import (
        DEFAULT_TIMEOUT_SECONDS,
        SafeHttpResponse,
        UnsafeTargetError,
        safe_http_request,
        validate_target_url,
    )
except ImportError:  # pragma: no cover - direct execution outside the repo
    from api_reporter import (
        ApiExecutionReport,
        ApiTestResult,
        redact_api_data,
        redact_headers,
    )
    from api_safety import (
        DEFAULT_TIMEOUT_SECONDS,
        SafeHttpResponse,
        UnsafeTargetError,
        safe_http_request,
        validate_target_url,
    )

# --------------------------------------------------------------------------- #
# Expected security headers
# --------------------------------------------------------------------------- #

#: Response headers checked by SEC-LIVE-HEADERS-001, with the reason each exists.
#: ``required`` headers are treated as defects when absent over any transport;
#: ``https_only`` headers are only meaningful over TLS and are reported as
#: NOT_APPLICABLE on a plain-HTTP loopback fixture rather than as failures.
SECURITY_HEADERS: Tuple[Dict[str, Any], ...] = (
    {
        "name": "x-content-type-options",
        "expected": "nosniff",
        "required": True,
        "why": "Without it a browser may re-interpret a response as HTML and execute it.",
    },
    {
        "name": "content-security-policy",
        "expected": None,
        "required": True,
        "why": "A policy is the main defence that limits the impact of an injected script.",
    },
    {
        "name": "x-frame-options",
        "expected": None,
        "required": False,
        "why": "Blocks framing-based clickjacking; superseded by CSP frame-ancestors.",
        "alternative": "content-security-policy",
    },
    {
        "name": "referrer-policy",
        "expected": None,
        "required": False,
        "why": "Stops full URLs (which may carry tokens) leaking to third parties.",
    },
    {
        "name": "strict-transport-security",
        "expected": None,
        "required": True,
        "https_only": True,
        "why": "Forces later requests onto TLS, preventing a downgrade on first contact.",
    },
)

#: Header values that disclose the server stack and ease targeted attacks.
VERBOSE_SERVER_HEADERS: Tuple[str, ...] = ("server", "x-powered-by", "x-aspnet-version")

#: Signatures of a leaked stack trace or internal diagnostic in a response body.
_TRACEBACK_SIGNATURES: Tuple[Tuple[str, str], ...] = (
    ("Traceback (most recent call last)", "Python traceback"),
    ("File \"/", "Python source path"),
    (".py\", line ", "Python source location"),
    ("at java.", "Java stack frame"),
    ("java.lang.", "Java exception class"),
    ("System.Exception", ".NET exception"),
    ("    at <anonymous>", "JavaScript stack frame"),
    ("node_modules/", "Node source path"),
    ("org.springframework", "Spring internals"),
    ("django.", "Django internals"),
    ("Werkzeug Debugger", "Werkzeug interactive debugger"),
    ("psycopg2.", "PostgreSQL driver internals"),
    ("SQLSTATE", "SQL error code"),
    ("ORA-0", "Oracle error code"),
    ("You have an error in your SQL syntax", "MySQL syntax error"),
)

#: Secret shapes that must never appear in an HTTP response body.
_RESPONSE_SECRET_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "cloud access key id"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (
        # No leading \b: a prefixed key name such as "stripe_api_key" must still
        # match, and an underscore is a word character so \b would exclude it.
        re.compile(
            r"(?i)(?:password|secret|api[_-]?key|client_secret|access_token|auth_token)"
            r"['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9\-\._~\+/]{12,}"
        ),
        "credential assignment",
    ),
    (
        re.compile(r"\b(?:sk_live_|rk_live_|xoxb-|xoxp-|ghp_|gho_|github_pat_|AIza)[A-Za-z0-9_\-]{10,}"),
        "provider API key",
    ),
    (re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb)://[^\s:]+:[^\s@]{4,}@"), "connection string with password"),
)


@dataclass
class SecurityTarget:
    """Everything a live security check needs to know about the service.

    Attributes:
        base_url: Service root, e.g. ``http://127.0.0.1:8099``.
        public_path: A path that must serve without authentication.
        protected_path: A path that must refuse an unauthenticated request.
        reflect_path: A path that echoes a query parameter back into the response.
        reflect_param: Query parameter name the reflect path echoes.
        error_path: A path that deliberately raises, to inspect error handling.
        login_path: A path that issues a session cookie on success.
        login_payload: Synthetic credentials posted to ``login_path``.
        user_a / user_b: Two synthetic identities, each a dict with at least
            ``token`` and ``resource_path``, used for cross-user isolation.
        state_change_path: A path whose POST changes state, for the CSRF check.
        redirect_path: A path that accepts a redirect destination parameter.
        redirect_param: Query parameter holding that destination.
        allow_external: Opt-in to a non-loopback target.
        timeout: Per-request timeout in seconds.
    """

    base_url: str
    public_path: str = "/"
    protected_path: Optional[str] = None
    reflect_path: Optional[str] = None
    reflect_param: str = "q"
    error_path: Optional[str] = None
    login_path: Optional[str] = None
    login_payload: Optional[Dict[str, str]] = None
    user_a: Optional[Dict[str, str]] = None
    user_b: Optional[Dict[str, str]] = None
    state_change_path: Optional[str] = None
    redirect_path: Optional[str] = None
    redirect_param: str = "next"
    allow_external: bool = False
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    def url(self, path: str) -> str:
        """Join the base URL with ``path`` without duplicating a slash."""
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"


# --------------------------------------------------------------------------- #
# Check helpers
# --------------------------------------------------------------------------- #


def _not_applicable(test_id: str, name: str, reason: str) -> ApiTestResult:
    """Build a NOT_APPLICABLE result. Missing configuration is never a pass."""
    return ApiTestResult(
        test_id=test_id,
        name=name,
        status="NOT_APPLICABLE",
        error_message=reason,
        remediation=(
            "Supply the corresponding target path to enable this check. Until then it is "
            "reported as not applicable, not as passing."
        ),
    )


def _unknown(test_id: str, name: str, response: SafeHttpResponse) -> ApiTestResult:
    """Build an UNKNOWN result for a request that never reached the service."""
    return ApiTestResult(
        test_id=test_id,
        name=name,
        status="UNKNOWN",
        duration_ms=response.duration_ms,
        url=response.url,
        method=response.method,
        error_message=response.error or "No response received from the target.",
        remediation=(
            "Confirm the service is running and reachable on the target URL, then rerun. "
            "An unreachable target yields no security evidence either way."
        ),
    )


def _request(target: SecurityTarget, path: str, **kwargs: Any) -> SafeHttpResponse:
    """Issue a bounded, loopback-validated request against ``target``."""
    kwargs.setdefault("timeout", target.timeout)
    kwargs.setdefault("allow_external", target.allow_external)
    return safe_http_request(target.url(path), **kwargs)


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #


def check_security_headers(target: SecurityTarget) -> ApiTestResult:
    """Verify the service sends the browser-protection response headers.

    Catalog: ``SEC-007``. Reference: OWASP Top 10:2025 A02 Security Misconfiguration.
    """
    test_id, name = "SEC-LIVE-HEADERS-001", "Security response headers present"
    response = _request(target, target.public_path)
    if response.status == 0:
        return _unknown(test_id, name, response)

    is_https = target.base_url.lower().startswith("https://")
    headers = response.headers
    missing: List[str] = []
    wrong: List[str] = []
    not_applicable: List[str] = []

    for spec in SECURITY_HEADERS:
        header_name = spec["name"]
        if spec.get("https_only") and not is_https:
            not_applicable.append(f"{header_name} (plain HTTP target)")
            continue
        value = headers.get(header_name)
        if value is None:
            alternative = spec.get("alternative")
            if alternative and headers.get(alternative):
                continue
            if spec["required"]:
                missing.append(header_name)
            else:
                not_applicable.append(f"{header_name} (advisory)")
            continue
        expected = spec.get("expected")
        if expected and expected.lower() not in value.lower():
            wrong.append(f"{header_name}={value!r} (expected to contain {expected!r})")

    disclosed = [h for h in VERBOSE_SERVER_HEADERS if headers.get(h)]

    problems = []
    if missing:
        problems.append(f"missing: {', '.join(missing)}")
    if wrong:
        problems.append(f"incorrect: {'; '.join(wrong)}")

    if problems:
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="FAIL",
            duration_ms=response.duration_ms,
            url=response.url,
            status_code=response.status,
            error_message=f"Security headers {'; '.join(problems)}.",
            evidence=str(redact_headers(headers)),
            remediation=(
                "Set the missing headers at the edge or in application middleware. "
                + "; ".join(
                    f"{spec['name']}: {spec['why']}"
                    for spec in SECURITY_HEADERS
                    if spec["name"] in missing
                )
            ),
            diagnostics=[
                {
                    "category": "SECURITY_HEADERS",
                    "missing": missing,
                    "incorrect": wrong,
                    "not_applicable": not_applicable,
                    "version_disclosure": disclosed,
                }
            ],
        )

    return ApiTestResult(
        test_id=test_id,
        name=name,
        status="PASS",
        duration_ms=response.duration_ms,
        url=response.url,
        status_code=response.status,
        evidence=(
            "All required security headers present"
            + (f"; advisory/not applicable: {', '.join(not_applicable)}" if not_applicable else "")
            + (f"; version disclosure via {', '.join(disclosed)}" if disclosed else "")
        ),
    )


def check_cookie_attributes(target: SecurityTarget) -> ApiTestResult:
    """Verify session cookies carry HttpOnly, Secure and SameSite.

    This is the authoritative evidence for cookie flags: frameworks often apply
    them centrally, so the static rule SEC-CONF-003 cannot decide the question.

    Catalog: ``SEC-006``.
    """
    test_id, name = "SEC-LIVE-COOKIE-001", "Session cookie security attributes"
    if not target.login_path:
        return _not_applicable(test_id, name, "No login_path configured, so no cookie is issued to inspect.")

    import json as _json

    body = _json.dumps(target.login_payload or {}).encode("utf-8")
    response = _request(
        target,
        target.login_path,
        method="POST",
        headers={"Content-Type": "application/json"},
        body=body,
    )
    if response.status == 0:
        return _unknown(test_id, name, response)

    set_cookie = response.headers.get("set-cookie", "")
    if not set_cookie:
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="UNKNOWN",
            duration_ms=response.duration_ms,
            url=response.url,
            method="POST",
            status_code=response.status,
            error_message="The login response set no cookie, so cookie attributes cannot be evaluated.",
            remediation=(
                "If the service authenticates with a bearer token rather than a cookie, this "
                "check is not applicable. If it should set a session cookie, the login path or "
                "synthetic credentials are wrong."
            ),
        )

    lowered = set_cookie.lower()
    is_https = target.base_url.lower().startswith("https://")
    missing: List[str] = []

    if "httponly" not in lowered:
        missing.append("HttpOnly (a script can read the session cookie)")
    if "samesite" not in lowered:
        missing.append("SameSite (the cookie rides along on cross-site requests)")
    if is_https and "secure" not in lowered:
        missing.append("Secure (the cookie may be sent over plain HTTP)")

    secure_note = ""
    if not is_https and "secure" not in lowered:
        secure_note = (
            " The Secure attribute is not enforced here because the target is plain HTTP; "
            "it must be set in any deployment served over TLS."
        )

    if missing:
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="FAIL",
            duration_ms=response.duration_ms,
            url=response.url,
            method="POST",
            status_code=response.status,
            error_message=f"Session cookie is missing: {'; '.join(missing)}.",
            evidence=redact_api_data(f"set-cookie: {set_cookie}"),
            remediation=(
                "Set HttpOnly, SameSite (Lax or Strict) and, over TLS, Secure on every "
                "session cookie." + secure_note
            ),
            diagnostics=[{"category": "COOKIE_ATTRIBUTES", "missing": missing}],
        )

    return ApiTestResult(
        test_id=test_id,
        name=name,
        status="PASS",
        duration_ms=response.duration_ms,
        url=response.url,
        method="POST",
        status_code=response.status,
        evidence="Session cookie carries the expected security attributes." + secure_note,
    )


def check_reflected_input_encoding(target: SecurityTarget) -> ApiTestResult:
    """Verify reflected input is encoded rather than returned as live markup.

    The probe is an inert, uniquely tagged string. The check asserts that the
    angle brackets come back encoded (or stripped), which is what distinguishes
    correct output handling from a reflected-XSS defect. It never attempts to
    execute anything.

    Catalog: ``SEC-003``. Reference: OWASP Top 10:2025 A05 Injection.
    """
    test_id, name = "SEC-LIVE-XSS-001", "Reflected input is encoded in output"
    if not target.reflect_path:
        return _not_applicable(test_id, name, "No reflect_path configured, so no reflection point is known.")

    marker = f"veriflow{uuid.uuid4().hex[:8]}"
    probe = f"<vf-probe>{marker}</vf-probe>"
    from urllib.parse import quote

    path = f"{target.reflect_path}?{target.reflect_param}={quote(probe)}"
    response = _request(target, path)
    if response.status == 0:
        return _unknown(test_id, name, response)

    body = response.body_text
    content_type = response.headers.get("content-type", "").lower()
    reflected_raw = probe in body or f"<vf-probe>{marker}" in body

    if marker not in body:
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="PASS",
            duration_ms=response.duration_ms,
            url=response.url,
            status_code=response.status,
            evidence="The probe value was not reflected into the response at all.",
        )

    if reflected_raw and ("html" in content_type or not content_type):
        snippet_start = max(0, body.find(marker) - 60)
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="FAIL",
            duration_ms=response.duration_ms,
            url=response.url,
            status_code=response.status,
            error_message=(
                "Input was reflected into an HTML response as unencoded markup, so the "
                "response renders attacker-supplied tags."
            ),
            evidence=body[snippet_start : snippet_start + 160],
            remediation=(
                "Render the value as text so the template engine escapes it, or encode "
                "'<', '>', '&', '\"' and \"'\" explicitly for the output context."
            ),
            diagnostics=[
                {
                    "category": "REFLECTED_INPUT_NOT_ENCODED",
                    "content_type": content_type,
                    "probe_marker": marker,
                }
            ],
        )

    return ApiTestResult(
        test_id=test_id,
        name=name,
        status="PASS",
        duration_ms=response.duration_ms,
        url=response.url,
        status_code=response.status,
        evidence=(
            f"The probe was reflected with its markup encoded or neutralised "
            f"(content-type: {content_type or 'unset'})."
        ),
    )


def check_authentication_required(target: SecurityTarget) -> ApiTestResult:
    """Verify an unauthenticated request to a protected path is refused.

    Catalog: ``AUTH-001``, ``ROLE-002``. Reference: OWASP A01 Broken Access Control.
    """
    test_id, name = "SEC-LIVE-AUTH-001", "Protected path refuses unauthenticated access"
    if not target.protected_path:
        return _not_applicable(test_id, name, "No protected_path configured.")

    response = _request(target, target.protected_path)
    if response.status == 0:
        return _unknown(test_id, name, response)

    if response.status in (401, 403):
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="PASS",
            duration_ms=response.duration_ms,
            url=response.url,
            status_code=response.status,
            evidence=f"Unauthenticated request refused with HTTP {response.status}.",
        )

    if response.status in (301, 302, 303, 307, 308):
        location = response.headers.get("location", "")
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="PASS",
            duration_ms=response.duration_ms,
            url=response.url,
            status_code=response.status,
            evidence=f"Unauthenticated request redirected to {redact_api_data(location) or 'a login route'}.",
        )

    return ApiTestResult(
        test_id=test_id,
        name=name,
        status="FAIL",
        duration_ms=response.duration_ms,
        url=response.url,
        status_code=response.status,
        error_message=(
            f"Protected path returned HTTP {response.status} without any credential: "
            "the access control gate is missing or not reached."
        ),
        evidence=redact_api_data(response.body_text[:200]),
        remediation=(
            "Enforce the authentication check in middleware or a route guard that runs "
            "before the handler, and add a regression test asserting HTTP 401 for an "
            "anonymous request."
        ),
        diagnostics=[{"category": "MISSING_AUTH_GATE", "observed_status": response.status}],
    )


def check_cross_user_isolation(target: SecurityTarget) -> ApiTestResult:
    """Verify user A's credential cannot read user B's resource (IDOR).

    Uses two synthetic identities supplied by the caller. Catalog: ``ROLE-004``,
    ``SEC-012``. Reference: OWASP A01 Broken Access Control.
    """
    test_id, name = "SEC-LIVE-IDOR-001", "Cross-user resource isolation enforced"
    if not (target.user_a and target.user_b):
        return _not_applicable(
            test_id, name, "Two synthetic identities (user_a and user_b) are required for this check."
        )

    victim_path = target.user_b.get("resource_path")
    attacker_token = target.user_a.get("token")
    if not victim_path or not attacker_token:
        return _not_applicable(
            test_id,
            name,
            "user_a must supply a 'token' and user_b must supply a 'resource_path'.",
        )

    response = _request(
        target,
        victim_path,
        headers={"Authorization": f"Bearer {attacker_token}"},
    )
    if response.status == 0:
        return _unknown(test_id, name, response)

    if response.status in (401, 403, 404):
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="PASS",
            duration_ms=response.duration_ms,
            url=response.url,
            status_code=response.status,
            evidence=(
                f"User A's credential was refused user B's resource with HTTP {response.status}."
            ),
        )

    return ApiTestResult(
        test_id=test_id,
        name=name,
        status="FAIL",
        duration_ms=response.duration_ms,
        url=response.url,
        status_code=response.status,
        error_message=(
            f"User A's credential read user B's resource (HTTP {response.status}). The "
            "handler authenticates the caller but does not check that the caller owns "
            "the record."
        ),
        evidence=redact_api_data(response.body_text[:200]),
        remediation=(
            "Scope the lookup to the authenticated principal (filter by owner in the "
            "query) rather than fetching by identifier and then checking. Add a "
            "regression test in which one user requests another user's record."
        ),
        diagnostics=[{"category": "BROKEN_OBJECT_LEVEL_AUTHORIZATION", "observed_status": response.status}],
    )


def check_error_disclosure(target: SecurityTarget) -> ApiTestResult:
    """Verify a server error returns a generic message, not an internal trace.

    Catalog: ``SEC-009``. Reference: OWASP A10 Mishandling of Exceptional Conditions.
    """
    test_id, name = "SEC-LIVE-ERROR-001", "Server errors disclose no internal detail"
    if not target.error_path:
        return _not_applicable(test_id, name, "No error_path configured, so no failure path can be triggered.")

    response = _request(target, target.error_path)
    if response.status == 0:
        return _unknown(test_id, name, response)

    body = response.body_text
    leaks = [label for signature, label in _TRACEBACK_SIGNATURES if signature in body]
    secrets = [label for pattern, label in _RESPONSE_SECRET_PATTERNS if pattern.search(body)]

    if leaks or secrets:
        disclosed = leaks + [f"{s} (value redacted)" for s in secrets]
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="FAIL",
            duration_ms=response.duration_ms,
            url=response.url,
            status_code=response.status,
            error_message=f"The error response disclosed: {', '.join(disclosed)}.",
            evidence=redact_api_data(body[:200]),
            remediation=(
                "Return a generic error body with a correlation id and log the detail "
                "server-side. Disable the debug error page in any deployed configuration."
            ),
            diagnostics=[
                {
                    "category": "ERROR_DETAIL_DISCLOSURE",
                    "signatures_found": leaks,
                    "secret_shapes_found": secrets,
                    "observed_status": response.status,
                }
            ],
        )

    status_note = ""
    if response.status < 500:
        status_note = (
            f" Note: the path returned HTTP {response.status} rather than a 5xx, so the "
            "server's failure path may not have been exercised."
        )

    return ApiTestResult(
        test_id=test_id,
        name=name,
        status="PASS",
        duration_ms=response.duration_ms,
        url=response.url,
        status_code=response.status,
        evidence=(
            "No traceback signature, internal path or secret shape found in the error body."
            + status_note
        ),
    )


def check_response_secret_leakage(target: SecurityTarget) -> ApiTestResult:
    """Verify the public response body carries no credential-shaped value.

    Catches the common defect of a server-rendered page or API payload embedding
    a key that was only meant for server use. Catalog: ``SEC-005``.
    """
    test_id, name = "SEC-LIVE-SECRET-001", "Public response leaks no credential"
    response = _request(target, target.public_path)
    if response.status == 0:
        return _unknown(test_id, name, response)

    found = [label for pattern, label in _RESPONSE_SECRET_PATTERNS if pattern.search(response.body_text)]
    if found:
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="FAIL",
            duration_ms=response.duration_ms,
            url=response.url,
            status_code=response.status,
            error_message=f"The response body contains {', '.join(found)} (value redacted).",
            evidence=redact_api_data(response.body_text[:200]),
            remediation=(
                "Remove the value from the response. Treat it as compromised and rotate it: "
                "anything served to a client has left your trust boundary."
            ),
            diagnostics=[{"category": "SECRET_IN_RESPONSE", "shapes_found": found}],
        )

    return ApiTestResult(
        test_id=test_id,
        name=name,
        status="PASS",
        duration_ms=response.duration_ms,
        url=response.url,
        status_code=response.status,
        evidence="No credential-shaped value found in the public response body.",
    )


def check_open_redirect(target: SecurityTarget) -> ApiTestResult:
    """Verify an externally supplied redirect destination is not honoured.

    Catalog: ``SEC-012``. The probe uses a reserved, non-resolvable domain from
    RFC 2606 so no request can reach a third party.
    """
    test_id, name = "SEC-LIVE-REDIRECT-001", "External redirect destination rejected"
    if not target.redirect_path:
        return _not_applicable(test_id, name, "No redirect_path configured.")

    from urllib.parse import quote

    hostile = "https://veriflow-probe.invalid/landing"
    path = f"{target.redirect_path}?{target.redirect_param}={quote(hostile, safe='')}"
    # Do not follow the redirect: the Location header is the evidence, and
    # following it would send a request to a host the safety policy never saw.
    response = _request(target, path, follow_redirects=False)
    if response.status == 0:
        return _unknown(test_id, name, response)

    location = response.headers.get("location", "")
    if "veriflow-probe.invalid" in location or "veriflow-probe.invalid" in response.body_text:
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="FAIL",
            duration_ms=response.duration_ms,
            url=response.url,
            status_code=response.status,
            error_message="The service redirected to an externally supplied destination.",
            evidence=f"location: {redact_api_data(location)}",
            remediation=(
                "Accept only relative paths, or validate the destination host against an "
                "allowlist before issuing the redirect."
            ),
            diagnostics=[{"category": "OPEN_REDIRECT", "location": location}],
        )

    return ApiTestResult(
        test_id=test_id,
        name=name,
        status="PASS",
        duration_ms=response.duration_ms,
        url=response.url,
        status_code=response.status,
        evidence="The external destination was not reflected into a redirect.",
    )


def check_csrf_protection(target: SecurityTarget) -> ApiTestResult:
    """Verify a state-changing request without a CSRF token is refused.

    Catalog: ``SEC-007``. Applies to cookie-authenticated, form-style endpoints;
    a purely token-authenticated API is not exposed to classic CSRF and the
    result says so rather than claiming a pass.
    """
    test_id, name = "SEC-LIVE-CSRF-001", "State-changing request without CSRF token refused"
    if not target.state_change_path:
        return _not_applicable(test_id, name, "No state_change_path configured.")

    response = _request(
        target,
        target.state_change_path,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body="veriflow_probe=1",
    )
    if response.status == 0:
        return _unknown(test_id, name, response)

    if response.status in (400, 401, 403, 419, 422):
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="PASS",
            duration_ms=response.duration_ms,
            url=response.url,
            method="POST",
            status_code=response.status,
            evidence=f"Token-less state-changing POST refused with HTTP {response.status}.",
        )

    if response.status == 405:
        return ApiTestResult(
            test_id=test_id,
            name=name,
            status="NOT_APPLICABLE",
            duration_ms=response.duration_ms,
            url=response.url,
            method="POST",
            status_code=405,
            error_message="The path does not accept POST, so it changes no state this way.",
        )

    return ApiTestResult(
        test_id=test_id,
        name=name,
        status="FAIL",
        duration_ms=response.duration_ms,
        url=response.url,
        method="POST",
        status_code=response.status,
        error_message=(
            f"A state-changing POST with no CSRF token returned HTTP {response.status}, so "
            "the request was accepted."
        ),
        evidence=redact_api_data(response.body_text[:200]),
        remediation=(
            "Require a per-session CSRF token on cookie-authenticated state changes, and set "
            "SameSite on the session cookie as a second layer. If the endpoint is meant to be "
            "authenticated by a bearer token only, reject cookie-only authentication on it."
        ),
        diagnostics=[{"category": "MISSING_CSRF_PROTECTION", "observed_status": response.status}],
    )


# --------------------------------------------------------------------------- #
# Registry and dispatch
# --------------------------------------------------------------------------- #

#: Every live check: ``(test_id, name, callable, catalog_ids)``.
LIVE_SECURITY_CHECKS: Tuple[Tuple[str, str, Callable[[SecurityTarget], ApiTestResult], Tuple[str, ...]], ...] = (
    ("SEC-LIVE-HEADERS-001", "Security response headers present", check_security_headers, ("SEC-008",)),
    ("SEC-LIVE-COOKIE-001", "Session cookie security attributes", check_cookie_attributes, ("SEC-007",)),
    ("SEC-LIVE-XSS-001", "Reflected input is encoded in output", check_reflected_input_encoding, ("SEC-001",)),
    ("SEC-LIVE-AUTH-001", "Protected path refuses unauthenticated access", check_authentication_required, ("ROLE-002", "AUTH-010")),
    ("SEC-LIVE-IDOR-001", "Cross-user resource isolation enforced", check_cross_user_isolation, ("SEC-004", "ROLE-004")),
    ("SEC-LIVE-ERROR-001", "Server errors disclose no internal detail", check_error_disclosure, ("SEC-009",)),
    ("SEC-LIVE-SECRET-001", "Public response leaks no credential", check_response_secret_leakage, ("SEC-006",)),
    ("SEC-LIVE-REDIRECT-001", "External redirect destination rejected", check_open_redirect, ("SEC-005",)),
    ("SEC-LIVE-CSRF-001", "State-changing request without CSRF token refused", check_csrf_protection, ("SEC-003",)),
)

#: Lookup for ``--check`` filtering and for regression tests.
LIVE_CHECKS_BY_ID: Dict[str, Tuple[str, Callable[[SecurityTarget], ApiTestResult], Tuple[str, ...]]] = {
    test_id: (name, fn, catalog) for test_id, name, fn, catalog in LIVE_SECURITY_CHECKS
}


def preview_live_checks(target: SecurityTarget) -> List[Dict[str, Any]]:
    """Describe the live checks that would run, sending no HTTP request.

    Preview is a pure function of the target configuration: it inspects which
    paths are configured and reports the rest as not applicable, so calling it
    can have no effect on the service.
    """
    planned: List[Dict[str, Any]] = []
    configured = {
        "SEC-LIVE-HEADERS-001": True,
        "SEC-LIVE-SECRET-001": True,
        "SEC-LIVE-COOKIE-001": bool(target.login_path),
        "SEC-LIVE-XSS-001": bool(target.reflect_path),
        "SEC-LIVE-AUTH-001": bool(target.protected_path),
        "SEC-LIVE-IDOR-001": bool(target.user_a and target.user_b),
        "SEC-LIVE-ERROR-001": bool(target.error_path),
        "SEC-LIVE-REDIRECT-001": bool(target.redirect_path),
        "SEC-LIVE-CSRF-001": bool(target.state_change_path),
    }
    for test_id, name, _fn, catalog in LIVE_SECURITY_CHECKS:
        planned.append(
            {
                "test_id": test_id,
                "name": name,
                "catalog_ids": list(catalog),
                "status": "NOT_RUN" if configured.get(test_id) else "NOT_APPLICABLE",
                "reason": (
                    "Planned; requires --execute to send requests."
                    if configured.get(test_id)
                    else "Required target path or synthetic identity is not configured."
                ),
            }
        )
    return planned


def run_live_security_checks(
    target: SecurityTarget,
    check_filter: Optional[Sequence[str]] = None,
) -> ApiExecutionReport:
    """Execute the live security checks against ``target``.

    Args:
        target: Validated service description.
        check_filter: Restrict to these check ids. ``None`` runs all of them.

    Returns:
        An :class:`ApiExecutionReport` whose results are redacted.

    Raises:
        UnsafeTargetError: when the base URL is not loopback and the caller did
            not opt in to an external target.
        ValueError: when ``check_filter`` names an unknown check. An unknown
            filter fails loudly rather than running nothing and reporting clean.
    """
    validate_target_url(target.base_url, allow_external=target.allow_external)

    selected = LIVE_SECURITY_CHECKS
    if check_filter:
        unknown = sorted(set(check_filter) - set(LIVE_CHECKS_BY_ID))
        if unknown:
            raise ValueError(
                f"Unknown security check id(s): {', '.join(unknown)}. "
                f"Available: {', '.join(sorted(LIVE_CHECKS_BY_ID))}"
            )
        wanted = set(check_filter)
        selected = tuple(c for c in LIVE_SECURITY_CHECKS if c[0] in wanted)

    report = ApiExecutionReport(
        target_url=target.base_url,
        environment_info={
            "engine": "veriflow-live-security-checks",
            "allow_external": target.allow_external,
            "timeout_seconds": target.timeout,
            "checks_selected": [c[0] for c in selected],
        },
    )

    for test_id, name, fn, _catalog in selected:
        try:
            report.add_result(fn(target))
        except UnsafeTargetError as exc:
            report.add_result(
                ApiTestResult(
                    test_id=test_id,
                    name=name,
                    status="BLOCKED",
                    error_message=f"Target rejected by safety policy: {exc}",
                    remediation=(
                        "Point the check at a local fixture, or pass the explicit external "
                        "authorization flag if you own the target and are permitted to test it."
                    ),
                )
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            report.add_result(
                ApiTestResult(
                    test_id=test_id,
                    name=name,
                    status="UNKNOWN",
                    error_message=f"Check raised an unexpected error: {type(exc).__name__}: {exc}",
                    remediation="Report this as a Veriflow defect with the target configuration used.",
                )
            )

    return report

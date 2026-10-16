#!/usr/bin/env python3
"""
Veriflow API and Integration Verification Engine.

Provides deterministic, non-destructive API verification routines:
- Health and readiness probes (API-HEALTH / RESL-006).
- Schema and contract validation (API-001).
- Client error formatting and input validation (API-002).
- Server error resilience and stack trace suppression (API-003 / SEC-009).
- Timeout and slow endpoint handling (API-004).
- Defensive malformed JSON handling (API-006).
- Rate limit handling and Retry-After compliance (API-007).
- Dependency outage and graceful degradation (API-008).
- Authentication required enforcement (AUTH-001 / API-002).
- Role-based authorization denial (ROLE-003 / ROLE-004).
- Data CRUD lifecycle consistency (DATA-001).
- HTTP method constraint enforcement (API-METHOD).

All routines use safe local loopback requests by default with bounded response capture.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Dict, List, Optional

# Ensure scripts dir is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from skills.veriflow.scripts.api_reporter import ApiTestResult
    from skills.veriflow.scripts.api_safety import SafeHttpResponse, safe_http_request
except ImportError:
    from api_reporter import ApiTestResult
    from api_safety import SafeHttpResponse, safe_http_request


def check_api_health(base_url: str, timeout: float = 5.0) -> ApiTestResult:
    """Validate that the service health probe returns HTTP 200 with status 'ok' (RESL-006)."""
    target_url = f"{base_url.rstrip('/')}/api/health"
    resp = safe_http_request(target_url, method="GET", timeout=timeout)

    if resp.is_timeout:
        return ApiTestResult(
            test_id="RESL-006",
            name="Service health probe verification",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="GET",
            error_message=f"Health probe timed out after {timeout:.1f}s",
            evidence=resp.error,
            remediation="Verify service is listening on target port and responding to /api/health.",
        )

    if resp.status != 200:
        return ApiTestResult(
            test_id="RESL-006",
            name="Service health probe verification",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="GET",
            status_code=resp.status,
            error_message=f"Expected HTTP 200 from health probe, got HTTP {resp.status}",
            evidence=resp.body_text[:200],
            remediation="Ensure /api/health returns HTTP 200 with JSON payload.",
        )

    if not resp.is_json:
        return ApiTestResult(
            test_id="RESL-006",
            name="Service health probe verification",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="GET",
            status_code=resp.status,
            error_message="Health probe did not return Content-Type: application/json",
            evidence=str(resp.headers),
            remediation="Configure /api/health to return application/json Content-Type.",
        )

    try:
        data = resp.json()
        if not isinstance(data, dict) or data.get("status") != "ok":
            return ApiTestResult(
                test_id="RESL-006",
                name="Service health probe verification",
                status="FAIL",
                duration_ms=resp.duration_ms,
                url=target_url,
                method="GET",
                status_code=resp.status,
                error_message="Health probe JSON payload missing 'status': 'ok'",
                evidence=resp.body_text[:200],
                remediation="Ensure /api/health payload includes {\"status\": \"ok\"}.",
            )
    except Exception as exc:
        return ApiTestResult(
            test_id="RESL-006",
            name="Service health probe verification",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="GET",
            status_code=resp.status,
            error_message=f"Failed to parse health probe JSON: {exc}",
            evidence=resp.body_text[:200],
        )

    return ApiTestResult(
        test_id="RESL-006",
        name="Service health probe verification",
        status="PASS",
        duration_ms=resp.duration_ms,
        url=target_url,
        method="GET",
        status_code=resp.status,
        response_body_snippet=resp.body_text[:200],
    )


def check_api_readiness(base_url: str, timeout: float = 5.0) -> ApiTestResult:
    """Validate that the readiness probe confirms service dependencies are operational (RESL-006)."""
    target_url = f"{base_url.rstrip('/')}/api/ready"
    resp = safe_http_request(target_url, method="GET", timeout=timeout)

    if resp.status != 200 or not resp.is_json:
        return ApiTestResult(
            test_id="API-READY",
            name="Service readiness probe verification",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="GET",
            status_code=resp.status,
            error_message=f"Expected HTTP 200 with JSON, got status {resp.status}",
            evidence=resp.body_text[:200],
        )

    try:
        data = resp.json()
        deps = data.get("dependencies", {})
        if not isinstance(deps, dict) or any(v != "connected" and v != "healthy" for v in deps.values()):
            return ApiTestResult(
                test_id="API-READY",
                name="Service readiness probe verification",
                status="FAIL",
                duration_ms=resp.duration_ms,
                url=target_url,
                method="GET",
                status_code=resp.status,
                error_message="Readiness dependencies not fully connected or healthy",
                evidence=str(deps),
            )
    except Exception as exc:
        return ApiTestResult(
            test_id="API-READY",
            name="Service readiness probe verification",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="GET",
            status_code=resp.status,
            error_message=f"Failed to parse readiness JSON: {exc}",
        )

    return ApiTestResult(
        test_id="API-READY",
        name="Service readiness probe verification",
        status="PASS",
        duration_ms=resp.duration_ms,
        url=target_url,
        method="GET",
        status_code=resp.status,
        response_body_snippet=resp.body_text[:200],
    )


def check_api_schema_contract(base_url: str, timeout: float = 5.0) -> ApiTestResult:
    """Validate primary GET endpoint conforms to schema expectations (API-001)."""
    target_url = f"{base_url.rstrip('/')}/api/items"
    resp = safe_http_request(target_url, method="GET", timeout=timeout)

    if resp.status != 200:
        return ApiTestResult(
            test_id="API-001",
            name="Happy-path API response schema and contract validation",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="GET",
            status_code=resp.status,
            error_message=f"Expected HTTP 200 from items endpoint, got {resp.status}",
            evidence=resp.body_text[:200],
        )

    if not resp.is_json:
        return ApiTestResult(
            test_id="API-001",
            name="Happy-path API response schema and contract validation",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="GET",
            status_code=resp.status,
            error_message="Response missing Content-Type: application/json",
            evidence=str(resp.headers),
        )

    try:
        items = resp.json()
        if not isinstance(items, list):
            return ApiTestResult(
                test_id="API-001",
                name="Happy-path API response schema and contract validation",
                status="FAIL",
                duration_ms=resp.duration_ms,
                url=target_url,
                method="GET",
                status_code=resp.status,
                error_message="Expected JSON array response",
                evidence=resp.body_text[:200],
            )

        if not items:
            return ApiTestResult(
                test_id="API-001",
                name="Happy-path API response schema and contract validation",
                status="FAIL",
                duration_ms=resp.duration_ms,
                url=target_url,
                method="GET",
                status_code=resp.status,
                error_message="Response array is empty; expected populated fixture items",
            )

        # Validate item schema contract
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                return ApiTestResult(
                    test_id="API-001",
                    name="Happy-path API response schema and contract validation",
                    status="FAIL",
                    duration_ms=resp.duration_ms,
                    url=target_url,
                    method="GET",
                    error_message=f"Item at index {idx} is not an object",
                )
            missing = [f for f in ("id", "name", "price") if f not in item]
            if missing:
                return ApiTestResult(
                    test_id="API-001",
                    name="Happy-path API response schema and contract validation",
                    status="FAIL",
                    duration_ms=resp.duration_ms,
                    url=target_url,
                    method="GET",
                    status_code=resp.status,
                    error_message=f"Item at index {idx} is missing required fields: {', '.join(missing)}",
                    evidence=json.dumps(item),
                    remediation="Ensure API returns all required schema fields without dropping keys.",
                )
    except Exception as exc:
        return ApiTestResult(
            test_id="API-001",
            name="Happy-path API response schema and contract validation",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="GET",
            status_code=resp.status,
            error_message=f"JSON parsing error: {exc}",
        )

    return ApiTestResult(
        test_id="API-001",
        name="Happy-path API response schema and contract validation",
        status="PASS",
        duration_ms=resp.duration_ms,
        url=target_url,
        method="GET",
        status_code=resp.status,
        response_body_snippet=resp.body_text[:200],
    )


def check_api_client_error_formatting(base_url: str, timeout: float = 5.0) -> ApiTestResult:
    """Validate that 4xx client errors return structured JSON without stack traces (API-002)."""
    target_url = f"{base_url.rstrip('/')}/api/items"
    # Send malformed raw JSON string
    malformed_raw = '{"name": "broken", "price": '
    resp = safe_http_request(
        target_url,
        method="POST",
        headers={"Content-Type": "application/json"},
        body=malformed_raw,
        timeout=timeout,
    )

    if resp.status != 400:
        return ApiTestResult(
            test_id="API-002",
            name="HTTP 4xx client error presentation and formatting",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="POST",
            status_code=resp.status,
            error_message=f"Expected HTTP 400 for malformed JSON, got HTTP {resp.status}",
            evidence=resp.body_text[:200],
            remediation="Ensure JSON parsing errors return HTTP 400 Bad Request.",
        )

    if not resp.is_json:
        return ApiTestResult(
            test_id="API-002",
            name="HTTP 4xx client error presentation and formatting",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="POST",
            status_code=resp.status,
            error_message="Client error response is not Content-Type: application/json",
            evidence=str(resp.headers),
        )

    # Check for stack trace leakage
    lower_body = resp.body_text.lower()
    if "traceback" in lower_body or "syntaxerror" in lower_body or "exception" in lower_body:
        return ApiTestResult(
            test_id="API-002",
            name="HTTP 4xx client error presentation and formatting",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="POST",
            status_code=resp.status,
            error_message="Client error response leaks internal stack trace or exception details",
            evidence=resp.body_text[:200],
            remediation="Suppress raw parser exceptions and return sanitized client error JSON.",
        )

    try:
        err_data = resp.json()
        if not isinstance(err_data, dict) or "error" not in err_data:
            return ApiTestResult(
                test_id="API-002",
                name="HTTP 4xx client error presentation and formatting",
                status="FAIL",
                duration_ms=resp.duration_ms,
                url=target_url,
                method="POST",
                status_code=resp.status,
                error_message="Structured error response missing 'error' key",
                evidence=resp.body_text[:200],
            )
    except Exception as exc:
        return ApiTestResult(
            test_id="API-002",
            name="HTTP 4xx client error presentation and formatting",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="POST",
            status_code=resp.status,
            error_message=f"Failed to parse error JSON: {exc}",
        )

    return ApiTestResult(
        test_id="API-002",
        name="HTTP 4xx client error presentation and formatting",
        status="PASS",
        duration_ms=resp.duration_ms,
        url=target_url,
        method="POST",
        status_code=resp.status,
        response_body_snippet=resp.body_text[:200],
    )


def check_api_input_validation(base_url: str, timeout: float = 5.0) -> ApiTestResult:
    """Validate that invalid inputs (missing required fields, negative values) are rejected with 400 (FORM-001)."""
    target_url = f"{base_url.rstrip('/')}/api/items"
    # Send empty name and negative price
    invalid_payload = json.dumps({"name": "", "price": -50.0})
    resp = safe_http_request(
        target_url,
        method="POST",
        headers={"Content-Type": "application/json"},
        body=invalid_payload,
        timeout=timeout,
    )

    if resp.status != 400:
        return ApiTestResult(
            test_id="FORM-001",
            name="Input validation and constraint enforcement",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="POST",
            status_code=resp.status,
            error_message=f"Expected HTTP 400 for invalid inputs, got HTTP {resp.status}",
            evidence=resp.body_text[:200],
            remediation="Validate payload fields on the server and reject empty names or negative values with HTTP 400.",
        )

    try:
        err_data = resp.json()
        if not isinstance(err_data, dict) or "details" not in err_data:
            return ApiTestResult(
                test_id="FORM-001",
                name="Input validation and constraint enforcement",
                status="FAIL",
                duration_ms=resp.duration_ms,
                url=target_url,
                method="POST",
                status_code=resp.status,
                error_message="Validation error missing 'details' array describing rejected fields",
                evidence=resp.body_text[:200],
            )
    except Exception as exc:
        return ApiTestResult(
            test_id="FORM-001",
            name="Input validation and constraint enforcement",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method="POST",
            status_code=resp.status,
            error_message=f"Failed to parse validation error JSON: {exc}",
        )

    return ApiTestResult(
        test_id="FORM-001",
        name="Input validation and constraint enforcement",
        status="PASS",
        duration_ms=resp.duration_ms,
        url=target_url,
        method="POST",
        status_code=resp.status,
        response_body_snippet=resp.body_text[:200],
    )


def check_api_auth_required(base_url: str, timeout: float = 5.0) -> ApiTestResult:
    """Validate that unauthenticated requests to protected API endpoints return 401 (AUTH-001)."""
    target_url = f"{base_url.rstrip('/')}/api/profile"

    # 1. Unauthenticated request must return 401
    unauth_resp = safe_http_request(target_url, method="GET", timeout=timeout)
    if unauth_resp.status != 401:
        return ApiTestResult(
            test_id="AUTH-001",
            name="Authentication requirement enforcement on protected endpoints",
            status="FAIL",
            duration_ms=unauth_resp.duration_ms,
            url=target_url,
            method="GET",
            status_code=unauth_resp.status,
            error_message=f"Expected HTTP 401 for unauthenticated request, got HTTP {unauth_resp.status}",
            evidence=unauth_resp.body_text[:200],
            remediation="Enforce authentication middleware on /api/profile to reject missing tokens with 401.",
        )

    # 2. Authenticated request with test token must succeed with 200
    auth_resp = safe_http_request(
        target_url,
        method="GET",
        headers={"Authorization": "Bearer token_user"},
        timeout=timeout,
    )
    if auth_resp.status != 200:
        return ApiTestResult(
            test_id="AUTH-001",
            name="Authentication requirement enforcement on protected endpoints",
            status="FAIL",
            duration_ms=auth_resp.duration_ms,
            url=target_url,
            method="GET",
            status_code=auth_resp.status,
            error_message=f"Expected HTTP 200 with valid bearer token, got HTTP {auth_resp.status}",
            evidence=auth_resp.body_text[:200],
        )

    return ApiTestResult(
        test_id="AUTH-001",
        name="Authentication requirement enforcement on protected endpoints",
        status="PASS",
        duration_ms=unauth_resp.duration_ms + auth_resp.duration_ms,
        url=target_url,
        method="GET",
        status_code=200,
        response_body_snippet=auth_resp.body_text[:200],
    )


def check_api_role_authorization_denial(base_url: str, timeout: float = 5.0) -> ApiTestResult:
    """Validate that requests with insufficient privileges return 403 Forbidden (ROLE-003)."""
    target_url = f"{base_url.rstrip('/')}/api/admin/metrics"

    # 1. Standard user token must be denied with 403
    user_resp = safe_http_request(
        target_url,
        method="GET",
        headers={"Authorization": "Bearer token_user"},
        timeout=timeout,
    )

    if user_resp.status != 403:
        return ApiTestResult(
            test_id="ROLE-003",
            name="Role-based access control and privilege denial",
            status="FAIL",
            duration_ms=user_resp.duration_ms,
            url=target_url,
            method="GET",
            status_code=user_resp.status,
            error_message=f"Expected HTTP 403 for standard user on admin endpoint, got HTTP {user_resp.status}",
            evidence=user_resp.body_text[:200],
            remediation="Verify role authorization checks require administrator privileges before serving admin metrics.",
        )

    # 2. Admin token must succeed with 200
    admin_resp = safe_http_request(
        target_url,
        method="GET",
        headers={"Authorization": "Bearer token_admin"},
        timeout=timeout,
    )

    if admin_resp.status != 200:
        return ApiTestResult(
            test_id="ROLE-003",
            name="Role-based access control and privilege denial",
            status="FAIL",
            duration_ms=admin_resp.duration_ms,
            url=target_url,
            method="GET",
            status_code=admin_resp.status,
            error_message=f"Expected HTTP 200 for admin user, got HTTP {admin_resp.status}",
            evidence=admin_resp.body_text[:200],
        )

    return ApiTestResult(
        test_id="ROLE-003",
        name="Role-based access control and privilege denial",
        status="PASS",
        duration_ms=user_resp.duration_ms + admin_resp.duration_ms,
        url=target_url,
        method="GET",
        status_code=200,
        response_body_snippet=admin_resp.body_text[:200],
    )



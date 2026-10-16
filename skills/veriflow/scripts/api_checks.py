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

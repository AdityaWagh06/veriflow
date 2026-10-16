#!/usr/bin/env python3
"""
Veriflow OpenAPI Contract Verification Checks & Execution Dispatcher.

Generates and executes contract verification checks directly from an OpenAPI specification:
- Static specification validation and component reference integrity
- Live endpoint reachability, status code, Content-Type, and body schema compliance
- Authentication enforcement on operations documenting security requirements
- Client input validation and boundary enforcement
- Enforces strict target safety (local loopback default) and credential redaction
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from skills.veriflow.scripts.api_reporter import (
    ApiExecutionReport,
    ApiTestResult,
    redact_api_data,
)
from skills.veriflow.scripts.api_safety import (
    UnsafeTargetError,
    is_local_target,
    safe_http_request,
)
from skills.veriflow.scripts.openapi_loader import (
    OpenApiOperation,
    OpenApiSpec,
    OpenApiSpecError,
)
from skills.veriflow.scripts.openapi_validator import (
    SchemaValidationError,
    validate_api_response,
    validate_schema,
)


@dataclass
class OpenApiCheckItem:
    """A generated check derived from an OpenAPI specification."""

    check_id: str
    name: str
    check_type: str  # "SPEC_VALIDATION" | "ENDPOINT_CONTRACT" | "AUTH_ENFORCEMENT" | "NEGATIVE_INPUT"
    path: str
    method: str
    description: str
    catalog_id: str
    expected_status: Optional[int] = 200
    operation: Optional[OpenApiOperation] = None
    is_destructive: bool = False


def generate_contract_checks(spec: OpenApiSpec) -> List[OpenApiCheckItem]:
    """Generate structured contract verification checks from a loaded OpenAPI specification."""
    checks: List[OpenApiCheckItem] = []

    # 1. Static Document Validation Check
    checks.append(
        OpenApiCheckItem(
            check_id="OA-SPEC-VALIDATION",
            name="OpenAPI document structure and reference integrity",
            check_type="SPEC_VALIDATION",
            path="/",
            method="N/A",
            description="Validates top-level keys, version conformance, and reference resolution.",
            catalog_id="API-001",
            expected_status=None,
            operation=None,
            is_destructive=False,
        )
    )

    operations = spec.get_operations()

    for op in operations:
        # Determine primary expected success status code (first 2xx or 200)
        expected_code = 200
        for code_str in op.responses.keys():
            if code_str.isdigit() and code_str.startswith("2"):
                expected_code = int(code_str)
                break

        # Path-specific catalog mapping
        is_health = op.path.rstrip("/") in ("/health", "/ready", "/api/health", "/api/ready")
        catalog_id = "RESL-006" if is_health else "API-001"

        is_destr = op.method.upper() in ("DELETE",)

        # 2. Main Contract Compliance Check
        check_id = f"OA-{op.method.upper()}-{op.path}"
        checks.append(
            OpenApiCheckItem(
                check_id=check_id,
                name=f"Contract validation for {op.method.upper()} {op.path}",
                check_type="ENDPOINT_CONTRACT",
                path=op.path,
                method=op.method.upper(),
                description=op.summary or f"Verify {op.method.upper()} {op.path} response schema contract",
                catalog_id=catalog_id,
                expected_status=expected_code,
                operation=op,
                is_destructive=is_destr,
            )
        )

        # 3. Authentication Enforcement Check (if security declared)
        if op.security is not None and len(op.security) > 0 and op.security != [{}]:
            checks.append(
                OpenApiCheckItem(
                    check_id=f"OA-AUTH-{op.method.upper()}-{op.path}",
                    name=f"Authentication gate enforcement on {op.method.upper()} {op.path}",
                    check_type="AUTH_ENFORCEMENT",
                    path=op.path,
                    method=op.method.upper(),
                    description="Verifies unauthenticated access receives HTTP 401 Unauthorized",
                    catalog_id="AUTH-001",
                    expected_status=401,
                    operation=op,
                    is_destructive=False,
                )
            )

        # 4. Input Validation Check (if required body or parameters exist)
        has_required_params = any(p.get("required") for p in op.parameters)
        has_required_body = bool(op.request_body and op.request_body.get("required"))
        if has_required_params or has_required_body:
            checks.append(
                OpenApiCheckItem(
                    check_id=f"OA-INPUT-{op.method.upper()}-{op.path}",
                    name=f"Input validation boundaries for {op.method.upper()} {op.path}",
                    check_type="NEGATIVE_INPUT",
                    path=op.path,
                    method=op.method.upper(),
                    description="Verifies missing or invalid inputs produce HTTP 400 client error",
                    catalog_id="API-002",
                    expected_status=400,
                    operation=op,
                    is_destructive=False,
                )
            )

    return checks


def _substitute_path_params(path: str, invalid: bool = False) -> str:
    """Substitute sample values for path parameters (e.g. {id} -> 1 or invalid-param)."""
    sub_val = "invalid-param" if invalid else "1"
    return re.sub(r"\{[a-zA-Z0-9_\-]+\}", sub_val, path)


def execute_contract_check(
    check: OpenApiCheckItem,
    base_url: str,
    spec: OpenApiSpec,
    timeout: float = 5.0,
    allow_external: bool = False,
    execute: bool = False,
) -> ApiTestResult:
    """
    Execute a single contract verification check.
    If execute=False, returns preview result with status NOT_RUN without network calls.
    """
    if not execute:
        return ApiTestResult(
            test_id=check.catalog_id,
            name=f"[{check.check_id}] {check.name}",
            status="NOT_RUN",
            url=f"{base_url.rstrip('/')}{check.path}" if check.path != "N/A" else "spec://local",
            method=check.method,
            status_code=check.expected_status,
        )

    # 1. Static Document Validation
    if check.check_type == "SPEC_VALIDATION":
        start_time = time.perf_counter()
        try:
            # Re-verify operations and component references
            ops = spec.get_operations()
            for op in ops:
                for status_code, resp in op.responses.items():
                    content = resp.get("content", {})
                    for media, media_obj in content.items():
                        schema = media_obj.get("schema")
                        if schema:
                            spec.resolve_schema(schema)
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return ApiTestResult(
                test_id=check.catalog_id,
                name=f"[{check.check_id}] {check.name}",
                status="PASS",
                duration_ms=duration_ms,
                url="spec://local",
                method="STATIC",
                status_code=None,
                response_body_snippet=f"Valid OpenAPI {spec.version} ({spec.title} v{spec.api_version}) with {len(ops)} operation(s)",
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return ApiTestResult(
                test_id=check.catalog_id,
                name=f"[{check.check_id}] {check.name}",
                status="FAIL",
                duration_ms=duration_ms,
                url="spec://local",
                method="STATIC",
                error_message=f"OpenAPI specification validation failed: {exc}",
                evidence=str(exc),
            )

    # Resolve target URL
    is_neg_path = (check.check_type == "NEGATIVE_INPUT" and "{" in check.path)
    concrete_path = _substitute_path_params(check.path, invalid=is_neg_path)
    target_url = f"{base_url.rstrip('/')}{concrete_path}"

    # Target safety check
    if not is_local_target(target_url) and not allow_external:
        return ApiTestResult(
            test_id=check.catalog_id,
            name=f"[{check.check_id}] {check.name}",
            status="BLOCKED",
            url=target_url,
            method=check.method,
            error_message=(
                f"Target URL '{target_url}' is outside local loopback boundaries. "
                "To test external destinations, pass --allow-external explicitly."
            ),
            remediation="Target local loopback server or provide --allow-external authorization flag.",
        )

    # Guard against destructive operations unless safe
    if check.is_destructive:
        return ApiTestResult(
            test_id=check.catalog_id,
            name=f"[{check.check_id}] {check.name}",
            status="MANUAL_REVIEW",
            url=target_url,
            method=check.method,
            error_message="Destructive HTTP operation (DELETE) skipped under default safety rules.",
            remediation="Execute state-changing operations against dedicated disposable fixtures only.",
        )

    # 2. Authentication Enforcement Check
    if check.check_type == "AUTH_ENFORCEMENT":
        resp = safe_http_request(target_url, method=check.method, timeout=timeout)
        if resp.status == 401:
            return ApiTestResult(
                test_id=check.catalog_id,
                name=f"[{check.check_id}] {check.name}",
                status="PASS",
                duration_ms=resp.duration_ms,
                url=target_url,
                method=check.method,
                status_code=resp.status,
                response_body_snippet=resp.body_text[:200],
            )
        elif resp.status == 200:
            return ApiTestResult(
                test_id=check.catalog_id,
                name=f"[{check.check_id}] {check.name}",
                status="FAIL",
                duration_ms=resp.duration_ms,
                url=target_url,
                method=check.method,
                status_code=resp.status,
                error_message=f"Expected HTTP 401 for unauthenticated request on protected operation, got HTTP {resp.status}",
                evidence=resp.body_text[:200],
                remediation="Ensure authentication middleware guards this operation against unauthenticated requests.",
            )
        else:
            return ApiTestResult(
                test_id=check.catalog_id,
                name=f"[{check.check_id}] {check.name}",
                status="PASS" if resp.status in (401, 403) else "FAIL",
                duration_ms=resp.duration_ms,
                url=target_url,
                method=check.method,
                status_code=resp.status,
                error_message=f"Received status code {resp.status} on authentication probe",
                evidence=resp.body_text[:200],
            )

    # 3. Negative Input Check
    if check.check_type == "NEGATIVE_INPUT":
        # Send empty request or empty JSON object where input is required
        headers = {"Content-Type": "application/json"}
        resp = safe_http_request(target_url, method=check.method, headers=headers, body="{}", timeout=timeout)
        if resp.status == 400:
            return ApiTestResult(
                test_id=check.catalog_id,
                name=f"[{check.check_id}] {check.name}",
                status="PASS",
                duration_ms=resp.duration_ms,
                url=target_url,
                method=check.method,
                status_code=resp.status,
                response_body_snippet=resp.body_text[:200],
            )
        elif resp.status in (200, 201):
            return ApiTestResult(
                test_id=check.catalog_id,
                name=f"[{check.check_id}] {check.name}",
                status="FAIL",
                duration_ms=resp.duration_ms,
                url=target_url,
                method=check.method,
                status_code=resp.status,
                error_message=f"Expected HTTP 400 Bad Request for missing required inputs, got HTTP {resp.status}",
                evidence=resp.body_text[:200],
                remediation="Enforce request validation schema on this endpoint to reject invalid/empty inputs.",
            )
        else:
            return ApiTestResult(
                test_id=check.catalog_id,
                name=f"[{check.check_id}] {check.name}",
                status="PASS" if resp.status in (400, 422) else "FAIL",
                duration_ms=resp.duration_ms,
                url=target_url,
                method=check.method,
                status_code=resp.status,
                error_message=f"Received status code {resp.status} on negative input test",
                evidence=resp.body_text[:200],
            )

    # 4. Main Endpoint Contract Check
    req_headers = {"Accept": "application/json"}
    if check.operation and check.operation.security and check.operation.security != [{}]:
        # Provide sample test token for authenticated fixture operations
        req_headers["Authorization"] = "Bearer token_user"

    # Construct minimal valid body if POST/PUT
    req_body = None
    if check.method in ("POST", "PUT", "PATCH") and check.operation and check.operation.request_body:
        content = check.operation.request_body.get("content", {})
        if "application/json" in content:
            req_headers["Content-Type"] = "application/json"
            schema = content["application/json"].get("schema", {})
            req_body = json.dumps(_generate_sample_from_schema(schema, spec))

    resp = safe_http_request(
        target_url,
        method=check.method,
        headers=req_headers,
        body=req_body,
        timeout=timeout,
    )

    if resp.error:
        return ApiTestResult(
            test_id=check.catalog_id,
            name=f"[{check.check_id}] {check.name}",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method=check.method,
            error_message=f"HTTP request failed: {resp.error}",
            evidence=resp.body_text[:200],
        )

    # Validate response contract
    body_data = resp.json() if resp.is_json else resp.body_text
    violations = validate_api_response(
        operation=check.operation,
        status_code=resp.status,
        headers=resp.headers,
        body_data=body_data,
        spec=spec,
    )

    if violations:
        diag_list = [v.to_dict() for v in violations]
        summary_errs = "; ".join(v.message for v in violations[:3])
        return ApiTestResult(
            test_id=check.catalog_id,
            name=f"[{check.check_id}] {check.name}",
            status="FAIL",
            duration_ms=resp.duration_ms,
            url=target_url,
            method=check.method,
            status_code=resp.status,
            error_message=f"Contract violation: {summary_errs}",
            evidence=resp.body_text[:300],
            remediation="Align API implementation with the documented OpenAPI response schema and status code.",
            diagnostics=diag_list,
        )

    return ApiTestResult(
        test_id=check.catalog_id,
        name=f"[{check.check_id}] {check.name}",
        status="PASS",
        duration_ms=resp.duration_ms,
        url=target_url,
        method=check.method,
        status_code=resp.status,
        response_body_snippet=resp.body_text[:200],
    )


def _generate_sample_from_schema(schema: Dict[str, Any], spec: Optional[OpenApiSpec]) -> Any:
    """Generate a minimal sample payload from a schema for testing requests."""
    if "$ref" in schema and spec:
        resolved = spec.resolve_schema(schema)
        return _generate_sample_from_schema(resolved, spec)

    schema_type = schema.get("type", "object")
    if schema_type == "string":
        return schema.get("example") or (schema.get("enum")[0] if schema.get("enum") else "sample")
    elif schema_type == "integer":
        return schema.get("example") or schema.get("minimum", 1)
    elif schema_type == "number":
        return schema.get("example") or schema.get("minimum", 1.0)
    elif schema_type == "boolean":
        return True
    elif schema_type == "array":
        item_schema = schema.get("items", {})
        return [_generate_sample_from_schema(item_schema, spec)]
    elif schema_type == "object":
        result = {}
        props = schema.get("properties", {})
        for prop_name, prop_schema in props.items():
            result[prop_name] = _generate_sample_from_schema(prop_schema, spec)
        return result
    return {}


def run_openapi_contract_verification(
    spec: OpenApiSpec,
    base_url: str = "http://127.0.0.1:8000",
    execute: bool = False,
    timeout: float = 5.0,
    allow_external: bool = False,
    check_filter: Optional[str] = None,
) -> ApiExecutionReport:
    """Run all contract verification checks against an API specification."""
    report = ApiExecutionReport(target_url=base_url if execute else "spec://local")
    checks = generate_contract_checks(spec)

    if check_filter:
        term = check_filter.lower()
        checks = [
            c for c in checks
            if term in c.check_id.lower()
            or term in c.name.lower()
            or term in c.path.lower()
            or term in c.catalog_id.lower()
            or (c.operation and c.operation.operation_id and term in c.operation.operation_id.lower())
        ]

    for check in checks:
        result = execute_contract_check(
            check=check,
            base_url=base_url,
            spec=spec,
            timeout=timeout,
            allow_external=allow_external,
            execute=execute,
        )
        report.add_result(result)

    return report

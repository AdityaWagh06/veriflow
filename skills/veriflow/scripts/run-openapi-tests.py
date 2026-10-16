#!/usr/bin/env python3
"""
Veriflow Standalone OpenAPI Contract Verification Runner CLI.

Validates OpenAPI specifications and executes contract checks against live or local services:
- Preview-only by default (shows planned checks and endpoints without sending requests).
- Requires --execute for live HTTP contract testing.
- Supports static specification validation (--validate-spec-only).
- Enforces local loopback target safety by default.
- Outputs human-readable summaries or machine-readable JSON (--json).
- Never leaks credentials or sensitive tokens in reports.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

# Ensure scripts dir and repo root are on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from skills.veriflow.scripts.api_reporter import (
    ApiExecutionReport,
    ApiTestResult,
    redact_api_data,
)
from skills.veriflow.scripts.api_safety import is_local_target
from skills.veriflow.scripts.openapi_checks import (
    execute_contract_check,
    generate_contract_checks,
    run_openapi_contract_verification,
)
from skills.veriflow.scripts.openapi_loader import (
    OpenApiBlockedError,
    OpenApiSpec,
    OpenApiSpecError,
    load_openapi_spec,
)


def _find_default_spec_file(search_dir: Path) -> Optional[Path]:
    """Look for standard OpenAPI specification file names in a directory."""
    candidates = [
        "openapi.json",
        "openapi.yaml",
        "openapi.yml",
        "swagger.json",
    ]
    for name in candidates:
        cand = search_dir / name
        if cand.is_file():
            return cand
    return None


def run_openapi_cli(
    spec_path: Optional[str] = None,
    target_url: Optional[str] = None,
    execute: bool = False,
    validate_spec_only: bool = False,
    check_filter: Optional[str] = None,
    timeout: float = 5.0,
    allow_external: bool = False,
    as_json: bool = False,
) -> int:
    """Run OpenAPI verification in static validation, preview, or live execution mode."""
    # 1. Locate and load specification
    file_to_load: Optional[Path] = None
    if spec_path:
        file_to_load = Path(spec_path).resolve()
        if not file_to_load.is_file():
            err_msg = f"OpenAPI specification file does not exist: {file_to_load}"
            if as_json:
                print(json.dumps({"status": "FAIL", "error": err_msg}, indent=2))
            else:
                print(f"Error: {err_msg}", file=sys.stderr)
            return 1
    else:
        file_to_load = _find_default_spec_file(Path.cwd())
        if not file_to_load:
            err_msg = "No OpenAPI specification specified and no openapi.json/openapi.yaml found in current directory."
            if as_json:
                print(json.dumps({"status": "BLOCKED", "error": err_msg}, indent=2))
            else:
                print(f"Error: {err_msg}", file=sys.stderr)
                print("Hint: Provide a specification with --spec <path_to_openapi.json>", file=sys.stderr)
            return 2

    try:
        spec = load_openapi_spec(file_to_load)
    except OpenApiBlockedError as exc:
        if as_json:
            print(json.dumps({
                "status": "BLOCKED",
                "error": str(exc),
                "remediation": "Install PyYAML (e.g. pip install pyyaml) or convert the specification to JSON.",
            }, indent=2))
        else:
            print(f"[BLOCKED] {exc}", file=sys.stderr)
        return 2
    except OpenApiSpecError as exc:
        if as_json:
            print(json.dumps({
                "status": "FAIL",
                "error": str(exc),
                "file": str(file_to_load),
            }, indent=2))
        else:
            print(f"Error validating OpenAPI document '{file_to_load.name}': {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if as_json:
            print(json.dumps({"status": "ERROR", "error": f"Unexpected error reading spec: {exc}"}, indent=2))
        else:
            print(f"Error reading specification: {exc}", file=sys.stderr)
        return 1

    # 2. Spec-Only Validation Mode
    if validate_spec_only:
        checks = generate_contract_checks(spec)
        spec_check = checks[0] if checks else None
        report = ApiExecutionReport(target_url=f"spec://{file_to_load.name}")

        if spec_check:
            res = execute_contract_check(spec_check, base_url="", spec=spec, execute=True)
            report.add_result(res)

        if as_json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print("=" * 60)
            print("Veriflow OpenAPI Specification Validation")
            print("=" * 60)
            print(f"Specification: {file_to_load.name} (OpenAPI {spec.version})")
            print(f"Title:         {spec.title} v{spec.api_version}")
            print(f"Operations:    {len(spec.get_operations())}")
            has_failure = any(r.status in ("FAIL", "BLOCKED") for r in report.results)
            if has_failure:
                print("Status:        [FAIL] Specification contains invalid or unresolved schema references.")
                for r in report.results:
                    if r.status in ("FAIL", "BLOCKED"):
                        print(f"Error:         {r.error_message}")
            else:
                print("Status:        [PASS] Document structure and schema references are valid.")
            print("=" * 60)
        has_failure = any(r.status in ("FAIL", "BLOCKED") for r in report.results)
        return 1 if has_failure else 0

    # 3. Determine target URL
    effective_url = target_url
    if not effective_url and spec.servers:
        # Check first server in spec if local
        candidate_server = spec.servers[0].get("url", "")
        if candidate_server and is_local_target(candidate_server):
            effective_url = candidate_server

    if not effective_url:
        effective_url = "http://127.0.0.1:8000"

    # 4. Preview Mode (Default)
    if not execute:
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

        preview_data = {
            "mode": "preview",
            "specification": str(file_to_load),
            "openapi_version": spec.version,
            "title": spec.title,
            "target_url": effective_url,
            "total_checks": len(checks),
            "filter": check_filter,
            "checks": [
                {
                    "check_id": c.check_id,
                    "catalog_id": c.catalog_id,
                    "name": c.name,
                    "check_type": c.check_type,
                    "method": c.method,
                    "path": c.path,
                    "expected_status": c.expected_status,
                }
                for c in checks
            ],
            "notice": "Preview mode: zero HTTP requests executed. Pass --execute to run live contract checks.",
        }

        if as_json:
            print(json.dumps(preview_data, indent=2))
        else:
            print("=" * 60)
            print("Veriflow OpenAPI Contract Verification — Preview Mode")
            print("=" * 60)
            print(f"Specification:   {file_to_load.name} (OpenAPI {spec.version})")
            print(f"API Title:       {spec.title} v{spec.api_version}")
            print(f"Target URL:      {effective_url}")
            print(f"Proposed Checks: {len(checks)}")
            print("-" * 60)
            for c in checks:
                print(f" - [{c.catalog_id}] {c.method} {c.path} -> {c.name}")
            print("-" * 60)
            print("Notice: Pass --execute to execute live contract verification checks.")
            print("=" * 60)
        return 0

    # 5. Live Execution Mode
    report = run_openapi_contract_verification(
        spec=spec,
        base_url=effective_url,
        execute=True,
        timeout=timeout,
        allow_external=allow_external,
        check_filter=check_filter,
    )

    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.format_text())

    counts = report.summary_counts()
    has_failures = counts.get("FAIL", 0) > 0 or counts.get("BLOCKED", 0) > 0 or counts.get("ERROR", 0) > 0
    return 1 if has_failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Veriflow Standalone OpenAPI Contract Verification Runner CLI",
    )
    parser.add_argument(
        "--spec",
        type=str,
        default=None,
        help="Path to the OpenAPI specification document (JSON or YAML).",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Base URL of the target service (defaults to http://127.0.0.1:8000 or spec servers).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute live HTTP contract verification checks against the target service.",
    )
    parser.add_argument(
        "--validate-spec-only",
        action="store_true",
        help="Validate the OpenAPI specification statically without running live endpoint tests.",
    )
    parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Filter checks by operationId, path keyword, or catalog ID.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Per-request HTTP timeout in seconds (default: 5.0).",
    )
    parser.add_argument(
        "--allow-external",
        action="store_true",
        help="Authorize testing external non-loopback destinations (prominently warned).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output results as formatted JSON.",
    )

    args = parser.parse_args()
    code = run_openapi_cli(
        spec_path=args.spec,
        target_url=args.url,
        execute=args.execute,
        validate_spec_only=args.validate_spec_only,
        check_filter=args.filter,
        timeout=args.timeout,
        allow_external=args.allow_external,
        as_json=args.as_json,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()

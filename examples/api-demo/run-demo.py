#!/usr/bin/env python3
"""
Veriflow API and Integration Verification Demo Runner.

Demonstrates end-to-end API verification against the deterministic local fixture:
1. Clean baseline: all mapped API checks pass deterministically.
2. Fault injection mode: injects targeted defects into the demo server to prove
   that the API test suite genuinely detects and reports real defects.
3. Preview mode: displays planned API checks without starting the server or making requests.

Usage:
    # Preview planned checks
    python examples/api-demo/run-demo.py --preview

    # Run clean demo suite
    python examples/api-demo/run-demo.py

    # Run with fault injection (e.g. broken schema contract)
    python examples/api-demo/run-demo.py --fault schema

    # Run with fault injection (e.g. stack trace leak on 500 error)
    python examples/api-demo/run-demo.py --fault stacktrace

    # Run with fault injection (e.g. unauthenticated access allowed)
    python examples/api-demo/run-demo.py --fault auth_bypass

    # Run with fault injection (e.g. non-admin permitted admin metrics)
    python examples/api-demo/run-demo.py --fault role_bypass

    # Run with fault injection (e.g. missing input validation)
    python examples/api-demo/run-demo.py --fault missing_validation

    # Run with fault injection (e.g. third-party dependency outage)
    python examples/api-demo/run-demo.py --fault dependency
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.api_checks import (
    get_api_checks_mapping,
    run_catalog_api_test,
)
from skills.veriflow.scripts.api_reporter import (
    ApiExecutionReport,
    ApiTestResult,
)
from skills.veriflow.scripts.api_safety import is_local_target


FAULT_MAP = {
    "schema": "fault_api_schema",
    "fault_api_schema": "fault_api_schema",
    "stacktrace": "fault_api_stacktrace",
    "fault_api_stacktrace": "fault_api_stacktrace",
    "auth_bypass": "fault_api_auth_bypass",
    "fault_api_auth_bypass": "fault_api_auth_bypass",
    "role_bypass": "fault_api_role_bypass",
    "fault_api_role_bypass": "fault_api_role_bypass",
    "missing_validation": "fault_api_missing_validation",
    "fault_api_missing_validation": "fault_api_missing_validation",
    "dependency": "fault_api_dependency",
    "fault_api_dependency": "fault_api_dependency",
}


def run_demo(
    fault: str | None = None,
    preview: bool = False,
    check_filter: str = "all",
    as_json: bool = False,
    base_url: str | None = None,
) -> int:
    """Run the API verification demo."""
    mappings = get_api_checks_mapping()

    if check_filter != "all":
        filter_lower = check_filter.lower()
        exact_match = [m for m in mappings if m.get("catalog_id", "").lower() == filter_lower]
        if exact_match:
            mappings = exact_match
        else:
            mappings = [
                m for m in mappings
                if filter_lower in m.get("catalog_id", "").lower()
                or filter_lower in m.get("function_name", "").lower()
                or filter_lower in m.get("name", "").lower()
            ]

    if not mappings:
        if as_json:
            print(json.dumps({"error": f"No checks matching filter '{check_filter}'"}, indent=2))
        else:
            print(f"Error: No checks matching filter '{check_filter}'", file=sys.stderr)
        return 1

    mapped_fault = FAULT_MAP.get(fault) if fault else None
    if fault and not mapped_fault:
        valid_faults = ", ".join(sorted(list({k for k in FAULT_MAP if not k.startswith("fault_")})))
        msg = f"Unknown fault '{fault}'. Valid options: {valid_faults}"
        if as_json:
            print(json.dumps({"error": msg}, indent=2))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        return 1

    if preview:
        preview_data = {
            "mode": "preview",
            "target": base_url or "Local Demo Application (in-memory fixture)",
            "fault_injected": mapped_fault or "none",
            "total_checks": len(mappings),
            "checks": [
                {
                    "catalog_id": m["catalog_id"],
                    "name": m["name"],
                    "category": m.get("category", "API"),
                    "function_name": m.get("function_name"),
                }
                for m in mappings
            ],
            "note": "Preview mode: no HTTP requests executed. Run without --preview to execute.",
        }
        if as_json:
            print(json.dumps(preview_data, indent=2))
        else:
            print("=" * 60)
            print("Veriflow API Verification Demo — Preview Mode")
            print("=" * 60)
            print(f"Target:          {preview_data['target']}")
            print(f"Fault Mode:      {mapped_fault or 'clean (no defects injected)'}")
            print(f"Checks to Run:   {len(mappings)}")
            print("-" * 60)
            for m in mappings:
                print(f"  [{m['catalog_id']}] {m['name']}")
            print("=" * 60)
            print("Run without --preview to execute checks against the fixture.")
        return 0

    # Execution Mode
    server = None

    try:
        if base_url:
            target_url = base_url
            if not is_local_target(target_url):
                print(f"Error: Target '{target_url}' is not a local loopback address.", file=sys.stderr)
                return 1
        else:
            server = DemoServer(port=0, fault=mapped_fault)
            target_url = server.start()

        report = ApiExecutionReport(target_url=target_url)

        for m in mappings:
            catalog_id = m["catalog_id"]
            result = run_catalog_api_test(catalog_id, target_url)
            report.add_result(result)

    finally:
        if server:
            server.stop()

    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.format_text())

    summary = report.summary_counts()
    has_failure = summary.get("FAIL", 0) > 0 or summary.get("BLOCKED", 0) > 0 or summary.get("ERROR", 0) > 0
    return 1 if has_failure else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Veriflow API and Integration Verification Demo Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview planned checks without making HTTP requests",
    )
    parser.add_argument(
        "--fault",
        type=str,
        default=None,
        help="Inject targeted defect: schema, stacktrace, auth_bypass, role_bypass, missing_validation, dependency",
    )
    parser.add_argument(
        "--filter",
        type=str,
        default="all",
        help="Filter checks by catalog ID or keyword (e.g. API-001, auth, schema)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Test an existing local loopback server instead of launching the demo fixture",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output results as JSON",
    )

    args = parser.parse_args()
    return run_demo(
        fault=args.fault,
        preview=args.preview,
        check_filter=args.filter,
        as_json=args.as_json,
        base_url=args.base_url,
    )


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Veriflow Standalone API & Integration Test Runner CLI.

Discovers and executes API verification checks against a target service or local fixture.
- Preview-only by default (shows proposed checks, endpoints, and methods without sending requests).
- Requires --execute for live HTTP execution.
- Restricts targets to local loopback addresses by default to prevent accidental external scanning.
- Outputs human-readable summaries or machine-readable JSON (--json).
- Never leaks passwords, bearer tokens, or credentials in reports.
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

try:
    from skills.veriflow.demo_app.server import DemoServer
    from skills.veriflow.scripts.api_checks import (
        get_api_checks_mapping,
        run_catalog_api_test,
    )
    from skills.veriflow.scripts.api_reporter import (
        ApiExecutionReport,
        ApiTestResult,
    )
    from skills.veriflow.scripts.api_safety import (
        UnsafeTargetError,
        validate_target_url,
    )
except ImportError:
    from demo_app.server import DemoServer
    from api_checks import (
        get_api_checks_mapping,
        run_catalog_api_test,
    )
    from api_reporter import (
        ApiExecutionReport,
        ApiTestResult,
    )
    from api_safety import (
        UnsafeTargetError,
        validate_target_url,
    )


def run_api_verification(
    target_url: Optional[str] = None,
    execute: bool = False,
    check_filter: str = "all",
    timeout: float = 5.0,
    allow_external: bool = False,
    as_json: bool = False,
) -> int:
    """Run API verification in preview mode (default) or live execution mode."""
    # Filter planned checks
    all_mappings = get_api_checks_mapping()
    if check_filter != "all":
        filter_lower = check_filter.lower()
        exact_category = [m for m in all_mappings if m.get("category", "").lower() == filter_lower]
        if exact_category:
            mappings = exact_category
        else:
            mappings = [
                m for m in all_mappings
                if filter_lower in m.get("catalog_id", "").lower()
                or filter_lower in m.get("check_function", "").lower()
                or filter_lower in m.get("name", "").lower()
                or filter_lower in m.get("endpoint", "").lower()
            ]
    else:
        mappings = all_mappings

    display_target = target_url or "http://127.0.0.1 (local deterministic fixture)"

    # Validate target safety if URL was explicitly provided
    if target_url:
        try:
            validate_target_url(target_url, allow_external=allow_external)
        except UnsafeTargetError as err:
            err_msg = f"Target safety validation failed: {err}"
            if as_json:
                print(json.dumps({"status": "BLOCKED", "error": err_msg}, indent=2))
            else:
                print(f"[BLOCKED] {err_msg}", file=sys.stderr)
            return 2

    # PREVIEW MODE (Default)
    if not execute:
        preview_data = {
            "mode": "preview",
            "target_url": display_target,
            "total_checks": len(mappings),
            "filter": check_filter,
            "checks": [
                {
                    "catalog_id": m["catalog_id"],
                    "name": m["name"],
                    "category": m.get("category", "API"),
                    "endpoint": m.get("endpoint", ""),
                    "method": m.get("method", "GET"),
                    "expected_status": m.get("expected_status", 200),
                }
                for m in mappings
            ],
            "notice": "Preview mode: zero HTTP requests made. Pass --execute to run live API verification.",
        }

        if as_json:
            print(json.dumps(preview_data, indent=2))
        else:
            print("=" * 60)
            print("Veriflow API Verification — Preview Mode")
            print("=" * 60)
            print(f"Target URL:      {display_target}")
            print(f"Filter:          {check_filter}")
            print(f"Proposed Checks: {len(mappings)}")
            print("-" * 60)
            for m in mappings:
                print(f" - [{m['catalog_id']}] {m['method']} {m['endpoint']} -> {m['name']}")
            print("-" * 60)
            print("Notice: Pass --execute to execute live HTTP verification checks.")
            print("=" * 60)
        return 0

    # LIVE EXECUTION MODE
    server: Optional[DemoServer] = None
    actual_url = target_url

    if not actual_url:
        try:
            server = DemoServer(port=0)
            actual_url = server.start()
        except Exception as e:
            err_msg = f"Failed to start local demo API fixture: {e}"
            if as_json:
                print(json.dumps({"status": "ERROR", "error": err_msg}, indent=2))
            else:
                print(f"[ERROR] {err_msg}", file=sys.stderr)
            return 1

    report = ApiExecutionReport(target_url=actual_url)

    try:
        for m in mappings:
            cid = m["catalog_id"]
            res = run_catalog_api_test(cid, actual_url, timeout=timeout)
            report.add_result(res)
    finally:
        if server:
            server.stop()

    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.format_text())

    counts = report.summary_counts()
    return 1 if counts.get("FAIL", 0) > 0 or counts.get("ERROR", 0) > 0 else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Veriflow Standalone API & Integration Test Runner CLI",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Target base URL (default: launches local demo API fixture on ephemeral port)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Explicitly authorize live HTTP execution (preview by default)",
    )
    parser.add_argument(
        "--filter",
        dest="check_filter",
        type=str,
        default="all",
        help="Filter checks by catalog ID, category (e.g. API, AUTH, RESL), or keyword",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Per-request HTTP timeout in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--allow-external",
        action="store_true",
        help="Explicitly allow non-local target destinations (strictly blocked by default)",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output structured JSON report",
    )

    args = parser.parse_args()
    code = run_api_verification(
        target_url=args.url,
        execute=args.execute,
        check_filter=args.check_filter,
        timeout=args.timeout,
        allow_external=args.allow_external,
        as_json=args.as_json,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()

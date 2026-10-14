#!/usr/bin/env python3
"""
Veriflow Browser Verification Demo Runner.

Demonstrates end-to-end browser verification against the local demo application:
1. Clean baseline: all 17 mapped journeys pass deterministically.
2. Fault injection mode: injects targeted defects into the demo server to prove
   that the browser test suite genuinely detects and reports real failures.
3. Preview mode: displays journey plan without browser execution.

Usage:
    # Preview planned checks
    python examples/browser-demo/run-demo.py --preview

    # Run clean demo suite
    python examples/browser-demo/run-demo.py

    # Run with fault injection (e.g. broken login navigation)
    python examples/browser-demo/run-demo.py --fault broken_login

    # Run with fault injection (e.g. unprotected route guard)
    python examples/browser-demo/run-demo.py --fault open_protected_route
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
from skills.veriflow.scripts.browser_detector import detect_browser_environment
from skills.veriflow.scripts.browser_journeys import (
    get_browser_catalog_mappings,
    launch_browser_context,
    run_catalog_browser_test,
)
from skills.veriflow.scripts.browser_reporter import (
    BrowserExecutionReport,
    BrowserTestResult,
)


def run_demo(
    fault: str | None = None,
    preview: bool = False,
    channel: str | None = None,
    journey_filter: str = "all",
    as_json: bool = False,
    headless: bool = True,
) -> int:
    """Run the browser verification demo."""
    env = detect_browser_environment(probe_launch=False)

    mappings = get_browser_catalog_mappings()
    if journey_filter != "all":
        exact_category = [m for m in mappings if m.get("category", "").lower() == journey_filter.lower()]
        if exact_category:
            mappings = exact_category
        else:
            mappings = [
                m for m in mappings
                if journey_filter.lower() in m.get("catalog_id", "").lower()
                or journey_filter.lower() in m.get("journey_function", "").lower()
                or journey_filter.lower() in m.get("name", "").lower()
            ]

    if preview:
        preview_data = {
            "mode": "preview",
            "target": "Demo Web Application",
            "fault_injected": fault or "none",
            "browser_environment": env.to_dict(),
            "total_journeys": len(mappings),
            "journeys": [
                {
                    "catalog_id": m["catalog_id"],
                    "name": m["name"],
                    "category": m.get("category", "GENERAL"),
                    "required_elements": m.get("required_elements", []),
                }
                for m in mappings
            ],
        }
        if as_json:
            print(json.dumps(preview_data, indent=2))
        else:
            print("=" * 60)
            print("Veriflow Browser Demo — Preview Mode")
            print("=" * 60)
            print(f"Browser Environment: {env.status} ({env.reason})")
            print(f"Target:              Local Demo Web Application")
            print(f"Fault Mode:          {fault or 'clean (no faults)'}")
            print(f"Journeys to Run:     {len(mappings)}")
            print("-" * 60)
            for m in mappings:
                reqs = f" [requires: {', '.join(m.get('required_elements', []))}]" if m.get("required_elements") else ""
                print(f" - [{m['catalog_id']}] {m['name']}{reqs}")
            print("-" * 60)
            print("Notice: Remove --preview to execute browser journeys.")
            print("=" * 60)
        return 0

    if env.status == "BLOCKED":
        if as_json:
            print(json.dumps({"status": "BLOCKED", "error": env.reason, "remediation": env.remediation}, indent=2))
        else:
            print(f"[BLOCKED] Browser automation cannot proceed: {env.reason}", file=sys.stderr)
            if env.remediation:
                print(f"Remediation: {env.remediation}", file=sys.stderr)
        return 2

    # Map fault flags to DemoServer fault string
    server_fault = ""
    if fault == "broken_login":
        server_fault = "faulty_redirect"
    elif fault == "open_protected_route":
        server_fault = "broken_auth_guard"
    elif fault == "console_error":
        server_fault = "runtime_error"
    elif fault in ("missing_validation", "broken_link", "server_500"):
        server_fault = fault

    server = DemoServer(port=0, fault=server_fault)
    base_url = server.start()

    selected_channel = channel or env.default_channel
    report = BrowserExecutionReport(
        target_url=base_url,
        browser_channel=selected_channel or "chromium",
        environment_info=env.to_dict(),
    )

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser, context = launch_browser_context(pw, channel=selected_channel, headless=headless)
            try:
                for m in mappings:
                    cid = m["catalog_id"]
                    context.clear_cookies()
                    page = context.new_page()
                    try:
                        res = run_catalog_browser_test(cid, page, base_url)
                        report.add_result(res)
                    finally:
                        page.close()
            finally:
                browser.close()
    except Exception as exc:
        err_res = BrowserTestResult(
            test_id="BROWSER-EXEC",
            name="Browser execution harness",
            status="FAIL",
            error_message=f"Fatal error during browser automation execution: {exc}",
        )
        report.add_result(err_res)
    finally:
        server.stop()

    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.format_text())

    counts = report.summary_counts()
    return 1 if counts.get("FAIL", 0) > 0 or counts.get("ERROR", 0) > 0 else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Veriflow Browser Verification Demo Runner",
    )
    parser.add_argument(
        "--fault",
        type=str,
        default=None,
        choices=[
            "broken_login",
            "open_protected_route",
            "missing_validation",
            "broken_link",
            "console_error",
            "server_500",
        ],
        help="Simulate a defect in the demo app to verify failure detection",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Show planned journeys without executing browser automation",
    )
    parser.add_argument(
        "--channel",
        type=str,
        default=None,
        help="Browser channel (e.g. chrome, msedge, chromium)",
    )
    parser.add_argument(
        "--filter",
        dest="journey_filter",
        type=str,
        default="all",
        help="Filter journeys by category (e.g. AUTH, NAV, FORM) or ID",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output structured JSON report",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in visible mode (default: headless)",
    )

    args = parser.parse_args()
    code = run_demo(
        fault=args.fault,
        preview=args.preview,
        channel=args.channel,
        journey_filter=args.journey_filter,
        as_json=args.as_json,
        headless=not args.headed,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Veriflow Standalone Browser Test Runner CLI.

Discovers and executes user-journey browser verification tests against a target web application.
- Preview-only by default (shows proposed journeys, required elements, and browser status).
- Requires --execute for live browser execution.
- Outputs human-readable report or machine-readable JSON (--json).
- Never leaks passwords, tokens, or credentials in outputs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List

# Ensure scripts dir and repo root are on sys.path for direct CLI invocation
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
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
except ImportError:
    from browser_detector import detect_browser_environment
    from browser_journeys import (
        get_browser_catalog_mappings,
        launch_browser_context,
        run_catalog_browser_test,
    )
    from browser_reporter import (
        BrowserExecutionReport,
        BrowserTestResult,
    )


def run_browser_verification(
    target_url: str | None = None,
    execute: bool = False,
    channel: str | None = None,
    journey_filter: str = "all",
    headless: bool = True,
    as_json: bool = False,
) -> int:
    """Run browser verification in preview or execution mode."""
    env = detect_browser_environment(probe_launch=False)

    mappings = get_browser_catalog_mappings()
    if journey_filter != "all":
        # Check if filter matches category exactly (case-insensitive)
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

    # Handle preview mode (default)
    if not execute:
        preview_data = {
            "mode": "preview",
            "browser_environment": env.to_dict(),
            "target_url": target_url or "http://127.0.0.1 (local demo fixture)",
            "selected_channel": channel or env.default_channel,
            "total_journeys": len(mappings),
            "journeys": mappings,
            "notice": "Preview mode: no browser launched. Pass --execute to run live browser journeys.",
        }

        if as_json:
            print(json.dumps(preview_data, indent=2))
        else:
            print("=" * 60)
            print("Veriflow Browser Verification — Preview Mode")
            print("=" * 60)
            print(f"Browser Environment: {env.status} ({env.reason})")
            if env.available_channels:
                print(f"Available Channels:  {', '.join(env.available_channels)}")
            print(f"Default Channel:     {channel or env.default_channel or 'None'}")
            print(f"Target URL:          {preview_data['target_url']}")
            print(f"Proposed Journeys:   {len(mappings)}")
            print("-" * 60)
            for m in mappings:
                reqs = f" [requires: {', '.join(m.get('required_elements', []))}]" if m.get("required_elements") else ""
                print(f" - [{m['catalog_id']}] {m['name']}{reqs}")
            print("-" * 60)
            print("Notice: Pass --execute to launch browser and run journeys.")
            print("=" * 60)
        return 0

    # Live execution requested: verify tool availability
    if env.status == "BLOCKED":
        if as_json:
            print(json.dumps({"status": "BLOCKED", "error": env.reason, "remediation": env.remediation}, indent=2))
        else:
            print(f"[BLOCKED] Browser automation cannot proceed: {env.reason}", file=sys.stderr)
            if env.remediation:
                print(f"Remediation: {env.remediation}", file=sys.stderr)
        return 2

    # Start demo server if target_url not provided
    server = None
    actual_url = target_url
    if not actual_url:
        try:
            try:
                from skills.veriflow.demo_app.server import DemoServer
            except ImportError:
                from demo_app.server import DemoServer
            server = DemoServer(port=0)
            actual_url = server.start()
        except Exception as e:
            err_msg = f"Failed to start local demo web application: {e}"
            if as_json:
                print(json.dumps({"status": "ERROR", "error": err_msg}, indent=2))
            else:
                print(f"[ERROR] {err_msg}", file=sys.stderr)
            return 1

    selected_channel = channel or env.default_channel
    report = BrowserExecutionReport(
        target_url=actual_url,
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
                        res = run_catalog_browser_test(cid, page, actual_url)
                        report.add_result(res)
                    finally:
                        page.close()
            finally:
                browser.close()
    except Exception as exc:
        err_res = BrowserTestResult(
            test_id="BROWSER-EXEC",
            name="Browser process execution",
            status="FAIL",
            error_message=f"Fatal error during browser automation execution: {exc}",
        )
        report.add_result(err_res)
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
        description="Veriflow Standalone Browser Test Runner CLI",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Target base URL (default: launches local demo web fixture)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Explicitly authorize live browser execution (preview by default)",
    )
    parser.add_argument(
        "--channel",
        type=str,
        default=None,
        help="Browser channel to use (e.g. chrome, msedge, chromium)",
    )
    parser.add_argument(
        "--journey",
        type=str,
        default="all",
        help="Filter journeys by category or function (e.g. auth, route, form, responsive, all)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in visible headed mode (default: headless)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit output in structured JSON format",
    )

    args = parser.parse_args()
    code = run_browser_verification(
        target_url=args.url,
        execute=args.execute,
        channel=args.channel,
        journey_filter=args.journey,
        headless=not args.headed,
        as_json=args.json,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()

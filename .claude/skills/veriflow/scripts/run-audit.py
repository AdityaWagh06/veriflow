#!/usr/bin/env python3
"""
Veriflow Full Audit — one command, one report, every engine.

Running the core runner, the security scanner and the production catalog
separately gives three different reports that nobody reads together. This
orchestrates all of it into a single, honest, shareable verdict:

  1. Project detection (what is this, what tools does it have).
  2. Static security scan (read-only, offline, always runs).
  3. Core check discovery, and execution when ``--execute`` is passed.
  4. A snapshot of the production-readiness catalog's scope (NOT filtered to
     this project — applicability still needs the judgement call the catalog
     guide describes; this is a scope summary, not a per-project verdict).
  5. One verdict, built only from what actually ran.

Design rules this script is built around, same as every other Veriflow
runner:

  - Preview by default. Without ``--execute`` nothing is run except the
    static security scan, which needs no prerequisite and executes no
    project code.
  - No vacuous verdicts. Without ``--execute`` the verdict is explicitly
    ``PREVIEW_ONLY``, never a pass. "READY" is never reported bare: the
    verdict is always ``NOT_READY`` or ``READY_WITH_RISKS``, because a
    passing run is evidence under the conditions tested, not a guarantee.
  - Shareable output. ``--markdown <path>`` writes the same findings as a
    clean Markdown report, suitable for a PR description or a teammate who
    was not in the terminal.

Windows PowerShell examples:

    python skills\\veriflow\\scripts\\run-audit.py .
    python skills\\veriflow\\scripts\\run-audit.py . --execute
    python skills\\veriflow\\scripts\\run-audit.py . --execute --json
    python skills\\veriflow\\scripts\\run-audit.py . --execute --markdown audit-report.md
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from security_scanner import format_scan_report, scan_project  # noqa: E402

#: run-checks.py has a hyphen in its filename, so it cannot be imported with a
#: normal `import` statement. Load it by path instead, the same way the test
#: suite does, so this script works whether or not the skill is installed.
_RUN_CHECKS_PATH = _SCRIPTS_DIR / "run-checks.py"
_spec = importlib.util.spec_from_file_location("veriflow_run_checks", _RUN_CHECKS_PATH)
_run_checks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_run_checks)
discover_checks = _run_checks.discover_checks

#: The production-readiness catalog this audit reports a scope snapshot from.
_CATALOG_PATH = _SCRIPTS_DIR.parent / "references" / "production-test-catalog.json"


def _load_catalog_snapshot() -> Optional[Dict[str, Any]]:
    """Return catalog totals, or None if the catalog file is unavailable.

    This is a scope summary of the whole catalog, not a per-project filtered
    result: deciding which cases actually apply to a given project is a
    judgement call the catalog guide assigns to the agent, not something this
    script infers from file contents.
    """
    try:
        data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return {
        "total_cases": len(data.get("test_cases", [])),
        "by_automation_status": data.get("summary", {}).get("by_automation_status", {}),
        "by_severity": data.get("summary", {}).get("by_severity", {}),
        "categories": len(data.get("categories", [])),
    }


def run_audit(
    root: Path | str,
    execute: bool = False,
    timeout: int = 60,
    security_categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run every available engine and assemble one audit result.

    Args:
        root: Project directory to audit.
        execute: When True, actually run the discovered checks. The static
            security scan runs either way: it is read-only and offline.
        timeout: Per-command timeout in seconds for executed checks.
        security_categories: Restrict the static scan to these categories.
            ``None`` scans every category.

    Returns:
        A JSON-serialisable dict. Every section records whether it actually
        executed, so the verdict can never be built from an assumption.
    """
    root_path = Path(root).resolve()
    timestamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    result: Dict[str, Any] = {
        "engine": "veriflow-audit",
        "root": str(root_path),
        "generated_at": timestamp,
        "executed": execute,
    }

    # ---- 1 & 3. Project detection + core checks (one call covers both) ---- #
    try:
        checks_report = discover_checks(root_path, execute=execute, timeout=timeout)
        checks_error = None
    except (FileNotFoundError, ValueError) as exc:
        checks_report = None
        checks_error = str(exc)

    result["project"] = {
        "detected_ecosystems": (checks_report or {}).get("detected_types", []),
        "package_manager": (checks_report or {}).get("package_manager", "unknown"),
        "error": checks_error,
    }

    # The core runner also discovers a "security" check that shells out to
    # run-security-tests.py. Section 2 below already runs that same static
    # scan in-process with full findings, so it is excluded here to avoid
    # running it twice and reporting it under two different shapes.
    discovered = [c for c in (checks_report or {}).get("discovered_checks", []) if c.get("name") != "security"]
    core_summary: Dict[str, int] = {}
    for check in discovered:
        status = check.get("status", "proposed")
        core_summary[status] = core_summary.get(status, 0) + 1

    result["core_checks"] = {
        "discovered_count": len(discovered),
        "checks": [
            {
                "name": c.get("name"),
                "ecosystem": c.get("ecosystem"),
                "status": c.get("status"),
                "executed": c.get("executed", False),
            }
            for c in discovered
        ],
        "summary": core_summary,
        "limitations": (checks_report or {}).get("limitations", []),
    }

    # ---- 2. Static security scan: always runs, read-only, offline -------- #
    try:
        security_report = scan_project(root_path, categories=security_categories)
        result["security"] = security_report.to_dict()
        result["security"]["_text"] = format_scan_report(security_report)
    except ValueError as exc:
        result["security"] = {"error": str(exc)}

    # ---- 4. Catalog scope snapshot ---------------------------------------- #
    result["catalog_snapshot"] = _load_catalog_snapshot()

    # ---- 5. Verdict -------------------------------------------------------- #
    result["verdict"] = _build_verdict(result)

    return result


def _build_verdict(result: Dict[str, Any]) -> Dict[str, Any]:
    """Derive a verdict strictly from what the audit actually observed.

    Never returns a bare "READY": a clean run is evidence under the
    conditions tested, not a guarantee, so the best outcome this function
    reports is READY_WITH_RISKS.
    """
    security = result.get("security", {})
    severity_counts = security.get("severity_counts", {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0})
    core_summary = result.get("core_checks", {}).get("summary", {})

    reasons: List[str] = []

    if not result["executed"]:
        return {
            "status": "PREVIEW_ONLY",
            "reasons": [
                "Core checks were only previewed, not executed. No pass/fail "
                "evidence exists yet for them.",
                "Re-run with --execute for an evidence-based verdict.",
            ],
        }

    critical_security = severity_counts.get("CRITICAL", 0)
    high_security = severity_counts.get("HIGH", 0)
    failed_checks = core_summary.get("FAIL", 0) if isinstance(core_summary, dict) else 0
    blocked_checks = core_summary.get("COMMAND_NOT_FOUND", 0) if isinstance(core_summary, dict) else 0

    if critical_security:
        reasons.append(f"{critical_security} CRITICAL static security finding(s).")
    if high_security:
        reasons.append(f"{high_security} HIGH static security finding(s).")
    if failed_checks:
        reasons.append(f"{failed_checks} executed check(s) FAILED.")

    if critical_security or failed_checks:
        status = "NOT_READY"
    elif high_security or blocked_checks:
        status = "READY_WITH_RISKS"
    else:
        status = "READY_WITH_RISKS"
        reasons.append(
            "No CRITICAL/HIGH findings and no executed-check failures observed. "
            "This covers only the checks and rules that actually ran -- not "
            "live security checks, API/OpenAPI/browser engines, or manual-review "
            "catalog cases, none of which this audit runs by default."
        )

    if blocked_checks:
        reasons.append(f"{blocked_checks} check(s) could not run (tool not found).")

    return {"status": status, "reasons": reasons}


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #


def format_text_report(result: Dict[str, Any]) -> str:
    """Render the audit as a readable terminal report."""
    lines = [
        "=" * 64,
        "Veriflow -- Full Project Audit",
        "=" * 64,
        f"Root:         {result['root']}",
        f"Generated:    {result['generated_at']}",
        f"Mode:         {'EXECUTED' if result['executed'] else 'PREVIEW (pass --execute to run checks)'}",
        "-" * 64,
    ]

    project = result["project"]
    lines.append("1. PROJECT")
    lines.append(f"   Ecosystems:      {', '.join(project['detected_ecosystems']) or '(none detected)'}")
    lines.append(f"   Package manager: {project['package_manager']}")
    if project.get("error"):
        lines.append(f"   Error:           {project['error']}")
    lines.append("")

    sec = result["security"]
    lines.append("2. STATIC SECURITY SCAN  (read-only, offline, always runs)")
    if "error" in sec:
        lines.append(f"   Error: {sec['error']}")
    else:
        counts = sec["severity_counts"]
        lines.append(
            f"   Findings: CRITICAL={counts['CRITICAL']} HIGH={counts['HIGH']} "
            f"MEDIUM={counts['MEDIUM']} LOW={counts['LOW']}  "
            f"(scanned {sec['files_scanned']} file(s), excluded {sec['excluded_files']})"
        )
        top = sorted(
            sec["findings"],
            key=lambda f: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(f["severity"], 4),
        )[:5]
        for finding in top:
            lines.append(f"     [{finding['severity']}] {finding['rule_id']}  {finding['file']}:{finding['line']}")
        if len(sec["findings"]) > len(top):
            lines.append(f"     ... and {len(sec['findings']) - len(top)} more (see --json for the full list)")
    lines.append("")

    core = result["core_checks"]
    lines.append(f"3. CORE CHECKS  ({core['discovered_count']} discovered)")
    for check in core["checks"]:
        status = check["status"] if check["executed"] else "NOT_RUN (preview)"
        lines.append(f"   [{status}] {check['name']} ({check['ecosystem']})")
    if core["summary"]:
        counts_str = " ".join(f"{k}={v}" for k, v in core["summary"].items() if v)
        if counts_str:
            lines.append(f"   Summary: {counts_str}")
    lines.append("")

    catalog = result.get("catalog_snapshot")
    lines.append("4. PRODUCTION-READINESS CATALOG SCOPE  (not filtered to this project)")
    if catalog:
        lines.append(
            f"   {catalog['total_cases']} cases across {catalog['categories']} categories available for "
            f"risk-based manual selection (see references/production-readiness.md)."
        )
        auto = catalog["by_automation_status"]
        lines.append(
            f"   automated_available={auto.get('automated_available', 0)}  "
            f"app_specific_automation={auto.get('app_specific_automation', 0)}  "
            f"manual_review={auto.get('manual_review', 0)}"
        )
    else:
        lines.append("   Catalog file not found; skipped.")
    lines.append("")

    verdict = result["verdict"]
    lines.append("-" * 64)
    lines.append(f"VERDICT: {verdict['status']}")
    for reason in verdict["reasons"]:
        lines.append(f"  - {reason}")
    lines.extend(
        [
            "-" * 64,
            "Safety Notice:",
            "  This verdict reflects only what actually ran. It does not cover live",
            "  security checks, API/OpenAPI/browser engines, dependency CVE auditing,",
            "  or catalog cases marked for manual review -- none of which run here by",
            "  default. It is not a guarantee of security or production readiness.",
            "=" * 64,
        ]
    )
    return "\n".join(lines)


def format_markdown_report(result: Dict[str, Any]) -> str:
    """Render the audit as a shareable Markdown report."""
    verdict = result["verdict"]
    sec = result["security"]
    core = result["core_checks"]
    project = result["project"]
    catalog = result.get("catalog_snapshot")

    lines = [
        "# Veriflow Full Audit",
        "",
        f"**Root:** `{result['root']}`  ",
        f"**Generated:** {result['generated_at']}  ",
        f"**Mode:** {'Executed' if result['executed'] else 'Preview only (pass `--execute` to run checks)'}",
        "",
        f"## Verdict: `{verdict['status']}`",
        "",
    ]
    for reason in verdict["reasons"]:
        lines.append(f"- {reason}")
    lines.append("")

    lines.append("## 1. Project")
    lines.append("")
    lines.append(f"- **Ecosystems:** {', '.join(project['detected_ecosystems']) or '_none detected_'}")
    lines.append(f"- **Package manager:** {project['package_manager']}")
    lines.append("")

    lines.append("## 2. Static Security Scan")
    lines.append("")
    lines.append("_Read-only, offline, always runs — no prerequisite._")
    lines.append("")
    if "error" in sec:
        lines.append(f"Error: {sec['error']}")
    else:
        counts = sec["severity_counts"]
        lines.append(
            f"| CRITICAL | HIGH | MEDIUM | LOW | Files scanned | Files excluded |\n"
            f"| :---: | :---: | :---: | :---: | :---: | :---: |\n"
            f"| {counts['CRITICAL']} | {counts['HIGH']} | {counts['MEDIUM']} | {counts['LOW']} | "
            f"{sec['files_scanned']} | {sec['excluded_files']} |"
        )
        lines.append("")
        if sec["findings"]:
            lines.append("| Severity | Rule | Location |")
            lines.append("| :--- | :--- | :--- |")
            for finding in sorted(
                sec["findings"],
                key=lambda f: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(f["severity"], 4),
            )[:15]:
                lines.append(
                    f"| {finding['severity']} | `{finding['rule_id']}` | "
                    f"`{finding['file']}:{finding['line']}` |"
                )
            if len(sec["findings"]) > 15:
                lines.append("")
                lines.append(f"_...and {len(sec['findings']) - 15} more. Run with `--json` for the full list._")
        else:
            lines.append("No findings.")
    lines.append("")

    lines.append(f"## 3. Core Checks ({core['discovered_count']} discovered)")
    lines.append("")
    if core["checks"]:
        lines.append("| Check | Ecosystem | Status |")
        lines.append("| :--- | :--- | :--- |")
        for check in core["checks"]:
            status = check["status"] if check["executed"] else "NOT_RUN (preview)"
            lines.append(f"| {check['name']} | {check['ecosystem']} | {status} |")
    else:
        lines.append("No checks discovered.")
    lines.append("")

    lines.append("## 4. Production-Readiness Catalog Scope")
    lines.append("")
    lines.append("_The full catalog's scope, not filtered to this project. Selecting which_")
    lines.append("_cases actually apply is a judgement call — see `references/production-readiness.md`._")
    lines.append("")
    if catalog:
        auto = catalog["by_automation_status"]
        lines.append(
            f"- **{catalog['total_cases']} cases** across **{catalog['categories']} categories**"
        )
        lines.append(f"- Automated available: {auto.get('automated_available', 0)}")
        lines.append(f"- App-specific automation required: {auto.get('app_specific_automation', 0)}")
        lines.append(f"- Manual review required: {auto.get('manual_review', 0)}")
    else:
        lines.append("Catalog file not found.")
    lines.append("")

    lines.append("## Safety Notice")
    lines.append("")
    lines.append(
        "This verdict reflects only what actually ran. It does not cover live security "
        "checks, the API/OpenAPI/browser engines, dependency CVE auditing, or catalog "
        "cases marked for manual review. It is not a guarantee of security or "
        "production readiness."
    )
    lines.append("")
    lines.append("---")
    lines.append("_Generated by [Veriflow](https://github.com/AdityaWagh06/veriflow)._")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run-audit.py",
        description=(
            "Veriflow Full Audit: project detection, static security scan, core checks "
            "and a catalog scope snapshot, combined into one verdict."
        ),
        epilog=(
            "Preview by default -- only the read-only static security scan runs. "
            "Pass --execute to actually run the discovered core checks."
        ),
    )
    parser.add_argument("root", nargs="?", default=".", help="Project directory to audit (default: current directory).")
    parser.add_argument("--execute", action="store_true", help="Execute discovered core checks, not just preview them.")
    parser.add_argument("--timeout", type=int, default=60, help="Per-command timeout in seconds (default: 60).")
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="Restrict the static security scan to a category (repeatable).",
    )
    parser.add_argument("--json", action="store_true", help="Emit the full structured JSON result.")
    parser.add_argument("--markdown", metavar="PATH", help="Also write a shareable Markdown report to PATH.")
    args = parser.parse_args(argv)

    try:
        result = run_audit(args.root, execute=args.execute, timeout=args.timeout, security_categories=args.categories)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.markdown:
        Path(args.markdown).write_text(format_markdown_report(result), encoding="utf-8")
        print(f"Markdown report written to: {args.markdown}", file=sys.stderr)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_text_report(result))

    return 1 if result["verdict"]["status"] == "NOT_READY" else 0


if __name__ == "__main__":
    sys.exit(main())

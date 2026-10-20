#!/usr/bin/env python3
"""
Veriflow Security Verification Demo Runner.

Demonstrates both halves of Veriflow's security phase against deterministic
local fixtures, and proves the checks genuinely detect defects rather than
merely passing on correct code.

1. Preview mode: shows the planned live checks without starting the fixture
   server and without sending a single HTTP request.
2. Clean baseline: the secure fixture passes all nine live checks.
3. Fault injection: one named fault breaks exactly one behaviour, and the
   matching check fails with a specific diagnosis.
4. Static scan: a deliberately vulnerable file versus its corrected form.

Everything binds to 127.0.0.1 on an OS-assigned port. The accounts and tokens
are fictional. No credential, no external host, and no destructive operation is
involved.

Usage:
    # Show the planned live checks, send nothing
    python examples/security-demo/run-demo.py --preview

    # Run the clean baseline: 9 live checks against the secure fixture
    python examples/security-demo/run-demo.py

    # Prove a specific check detects its defect
    python examples/security-demo/run-demo.py --fault reflected_xss
    python examples/security-demo/run-demo.py --fault cross_user_leak
    python examples/security-demo/run-demo.py --fault stack_trace_leak

    # Run every fault in sequence and report the detection matrix
    python examples/security-demo/run-demo.py --all-faults

    # Demonstrate the static scanner on vulnerable vs corrected source
    python examples/security-demo/run-demo.py --static

    # Machine-readable output
    python examples/security-demo/run-demo.py --format json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

DEMO_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEMO_DIR.parent.parent
SCRIPTS_DIR = REPO_ROOT / "skills" / "veriflow" / "scripts"

for path in (str(REPO_ROOT), str(SCRIPTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from security_checks import (  # noqa: E402
    LIVE_SECURITY_CHECKS,
    SecurityTarget,
    preview_live_checks,
    run_live_security_checks,
)
from security_scanner import format_scan_report, scan_project  # noqa: E402

_spec = importlib.util.spec_from_file_location("veriflow_security_demo_server", DEMO_DIR / "server.py")
_server_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_server_module)
SecurityFixtureServer = _server_module.SecurityFixtureServer
FAULT_MODES = _server_module.FAULT_MODES

#: Which live check each fault is expected to break.
FAULT_TO_CHECK: Dict[str, str] = {
    "missing_headers": "SEC-LIVE-HEADERS-001",
    "insecure_cookie": "SEC-LIVE-COOKIE-001",
    "reflected_xss": "SEC-LIVE-XSS-001",
    "open_protected_route": "SEC-LIVE-AUTH-001",
    "cross_user_leak": "SEC-LIVE-IDOR-001",
    "stack_trace_leak": "SEC-LIVE-ERROR-001",
    "secret_in_response": "SEC-LIVE-SECRET-001",
    "open_redirect": "SEC-LIVE-REDIRECT-001",
    "missing_csrf": "SEC-LIVE-CSRF-001",
}

#: A file with one defect per scanner category, for the static demonstration.
VULNERABLE_SAMPLE = '''\
import hashlib
import pickle
import subprocess

DB_PASSWORD = "Kf8sLq2mXz9vNb4tRw7p"
DEBUG = True


def run(name):
    subprocess.run("ls " + name, shell=True)


def lookup(cursor, user_id):
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")


def load(blob):
    return pickle.loads(blob)


def digest(password):
    return hashlib.md5(password.encode()).hexdigest()
'''

#: The same file, corrected. The scanner must report nothing here.
CORRECTED_SAMPLE = '''\
import hashlib
import json
import os
import subprocess

DB_PASSWORD = os.environ["DB_PASSWORD"]
DEBUG = os.getenv("DEBUG", "0") == "1"


def run(name):
    subprocess.run(["ls", name], check=True)


def lookup(cursor, user_id):
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))


def load(blob):
    return json.loads(blob)


def digest(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
'''


def demo_target(base_url: str) -> SecurityTarget:
    """Fully configured target for the local security fixture."""
    return SecurityTarget(
        base_url=base_url,
        public_path="/",
        protected_path="/account",
        reflect_path="/echo",
        reflect_param="q",
        error_path="/boom",
        login_path="/login",
        login_payload={"username": "vf-fixture-user", "password": "vf-fixture-password"},
        user_a={"token": "vf-token-user-a"},
        user_b={"resource_path": "/records/rec-b"},
        state_change_path="/profile/update",
        redirect_path="/go",
        redirect_param="next",
    )


def run_preview(as_json: bool) -> int:
    """Show the planned live checks. Starts no server and sends no request."""
    # A placeholder loopback URL: preview is a pure function of configuration.
    planned = preview_live_checks(demo_target("http://127.0.0.1:0"))

    if as_json:
        print(json.dumps({"mode": "preview", "planned_checks": planned}, indent=2))
        return 0

    print("=" * 64)
    print("Veriflow Security Demo -- Preview Mode")
    print("=" * 64)
    print(f"Planned live checks: {len(planned)}")
    print("-" * 64)
    for item in planned:
        print(f"  [{item['status']}] {item['test_id']}: {item['name']}")
        print(f"      Catalog: {', '.join(item['catalog_ids'])}")
    print("-" * 64)
    print("No fixture server was started and no HTTP request was sent.")
    print("Run without --preview to execute these checks against the local fixture.")
    print("=" * 64)
    return 0


def run_live(faults: Optional[set], as_json: bool) -> int:
    """Run the live checks against the secure or a faulted fixture."""
    mode = ", ".join(sorted(faults)) if faults else "secure (no faults)"
    expected = FAULT_TO_CHECK.get(next(iter(faults))) if faults and len(faults) == 1 else None

    with SecurityFixtureServer(faults) as server:
        report = run_live_security_checks(demo_target(server.base_url))

    counts = report.summary_counts()

    if as_json:
        print(json.dumps({"mode": mode, "expected_failure": expected, **report.to_dict()}, indent=2))
        return 1 if counts["FAIL"] else 0

    print("=" * 64)
    print("Veriflow Security Demo -- Live Checks")
    print("=" * 64)
    print(f"Fixture mode: {mode}")
    if expected:
        print(f"Expected to fail: {expected}")
    print()
    print(report.format_text())

    if faults and expected:
        actual = next(r.status for r in report.results if r.test_id == expected)
        collateral = sorted(r.test_id for r in report.results if r.status == "FAIL" and r.test_id != expected)
        print()
        print("Fault detection result:")
        print(f"  {expected} = {actual}" + ("  (as expected)" if actual == "FAIL" else "  (NOT DETECTED)"))
        if collateral:
            print(f"  Other checks that also failed: {', '.join(collateral)}")

    return 1 if counts["FAIL"] else 0


def run_all_faults(as_json: bool) -> int:
    """Run every fault in turn and report whether each was detected."""
    matrix: List[Dict[str, Any]] = []

    with SecurityFixtureServer() as server:
        clean = run_live_security_checks(demo_target(server.base_url))
    clean_counts = clean.summary_counts()

    for fault in sorted(FAULT_MODES):
        check_id = FAULT_TO_CHECK[fault]
        with SecurityFixtureServer({fault}) as server:
            report = run_live_security_checks(demo_target(server.base_url))
        by_id = {r.test_id: r for r in report.results}
        matrix.append(
            {
                "fault": fault,
                "expected_check": check_id,
                "observed_status": by_id[check_id].status,
                "detected": by_id[check_id].status == "FAIL",
                "collateral_failures": sorted(
                    r.test_id for r in report.results if r.status == "FAIL" and r.test_id != check_id
                ),
                "diagnosis": by_id[check_id].error_message,
            }
        )

    all_detected = all(row["detected"] for row in matrix)
    clean_passed = clean_counts["FAIL"] == 0

    if as_json:
        print(
            json.dumps(
                {
                    "clean_baseline": clean_counts,
                    "fault_matrix": matrix,
                    "all_faults_detected": all_detected,
                    "clean_fixture_passed": clean_passed,
                },
                indent=2,
            )
        )
        return 0 if (all_detected and clean_passed) else 1

    print("=" * 64)
    print("Veriflow Security Demo -- Fault Detection Matrix")
    print("=" * 64)
    print(
        f"Clean baseline: PASS={clean_counts['PASS']} FAIL={clean_counts['FAIL']} "
        f"-> {'secure fixture passes' if clean_passed else 'UNEXPECTED FAILURE'}"
    )
    print("-" * 64)
    for row in matrix:
        marker = "DETECTED    " if row["detected"] else "NOT DETECTED"
        print(f"  [{marker}] {row['fault']:22} -> {row['expected_check']} = {row['observed_status']}")
        if row["collateral_failures"]:
            print(f"                 collateral: {', '.join(row['collateral_failures'])}")
    print("-" * 64)
    print(f"All {len(matrix)} faults detected: {all_detected}")
    print()
    print("A check that passes on correct code proves nothing on its own. This")
    print("matrix is the evidence that each check fails on the specific defect it")
    print("covers, and does not fire on the others.")
    print("=" * 64)
    return 0 if (all_detected and clean_passed) else 1


def run_static(as_json: bool) -> int:
    """Scan a vulnerable sample, then its corrected form."""
    results: Dict[str, Any] = {}

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "app.py").write_text(VULNERABLE_SAMPLE, encoding="utf-8")
        vulnerable = scan_project(tmp)
        results["vulnerable"] = vulnerable.to_dict()

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "app.py").write_text(CORRECTED_SAMPLE, encoding="utf-8")
        corrected = scan_project(tmp)
        results["corrected"] = corrected.to_dict()

    if as_json:
        print(json.dumps(results, indent=2))
        return 0

    print("=" * 64)
    print("Veriflow Security Demo -- Static Scan (read-only, offline)")
    print("=" * 64)
    print()
    print("### 1. Deliberately vulnerable source")
    print()
    print(format_scan_report(vulnerable))
    print()
    print("### 2. The same file, corrected")
    print()
    print(format_scan_report(corrected))
    print()
    print("-" * 64)
    print(
        f"Vulnerable: {len(vulnerable.findings)} finding(s). "
        f"Corrected: {len(corrected.findings)} finding(s)."
    )
    print("Note that the credential value never appears in either report.")
    print("=" * 64)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Veriflow security verification demo against local fixtures.",
        epilog="Everything runs on 127.0.0.1 with synthetic accounts. Nothing external is contacted.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="Show planned checks; send nothing.")
    mode.add_argument(
        "--fault",
        action="append",
        dest="faults",
        choices=sorted(FAULT_MODES),
        help="Activate a fault so the matching check fails (repeatable).",
    )
    mode.add_argument("--all-faults", action="store_true", help="Run every fault and print the detection matrix.")
    mode.add_argument("--static", action="store_true", help="Demonstrate the static scanner only.")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    args = parser.parse_args(argv)
    as_json = args.format == "json"

    if args.preview:
        return run_preview(as_json)
    if args.static:
        return run_static(as_json)
    if args.all_faults:
        return run_all_faults(as_json)
    return run_live(set(args.faults) if args.faults else None, as_json)


if __name__ == "__main__":
    sys.exit(main())

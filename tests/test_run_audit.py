"""
Tests for the Veriflow Full Audit orchestrator.

The core claim being tested: the verdict is derived strictly from what
actually ran, never asserted. A clean fixture must produce READY_WITH_RISKS
(never a bare "READY" -- that overclaims), a vulnerable fixture must produce
NOT_READY, and a preview-only run must never produce either.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_CLI = REPO_ROOT / "skills" / "veriflow" / "scripts" / "run-audit.py"

_spec = importlib.util.spec_from_file_location("veriflow_run_audit", AUDIT_CLI)
run_audit_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_audit_module)

run_audit = run_audit_module.run_audit
format_text_report = run_audit_module.format_text_report
format_markdown_report = run_audit_module.format_markdown_report

CLEAN_SAMPLE = '''\
import json
import os


def load(blob):
    return json.loads(blob)


def get_key():
    return os.environ["API_KEY"]
'''

VULNERABLE_SAMPLE = '''\
import pickle
import subprocess


def run(name):
    subprocess.run("ls " + name, shell=True)


def load(blob):
    return pickle.loads(blob)
'''


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(AUDIT_CLI), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


class TestAuditPreviewMode(unittest.TestCase):
    """Without --execute, nothing but the static scan runs, and the verdict says so."""

    def test_preview_verdict_is_never_a_pass_or_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(CLEAN_SAMPLE, encoding="utf-8")
            result = run_audit(tmp, execute=False)
            self.assertEqual(result["verdict"]["status"], "PREVIEW_ONLY")
            self.assertFalse(result["executed"])

    def test_preview_still_runs_the_static_security_scan(self):
        """The static scan needs no --execute: it is read-only and offline."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(VULNERABLE_SAMPLE, encoding="utf-8")
            result = run_audit(tmp, execute=False)
            self.assertGreater(result["security"]["total_findings"], 0)

    def test_preview_marks_core_checks_as_not_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
            result = run_audit(tmp, execute=False)
            for check in result["core_checks"]["checks"]:
                self.assertFalse(check["executed"])


class TestAuditVerdictHonesty(unittest.TestCase):
    """The verdict must track real findings, in both directions."""

    def test_clean_fixture_is_ready_with_risks_never_bare_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(CLEAN_SAMPLE, encoding="utf-8")
            result = run_audit(tmp, execute=True)
            self.assertEqual(result["verdict"]["status"], "READY_WITH_RISKS")
            # "READY" must never appear as a bare, unqualified verdict string.
            self.assertNotEqual(result["verdict"]["status"], "READY")

    def test_vulnerable_fixture_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(VULNERABLE_SAMPLE, encoding="utf-8")
            result = run_audit(tmp, execute=True)
            self.assertEqual(result["verdict"]["status"], "NOT_READY")
            reasons = " ".join(result["verdict"]["reasons"])
            self.assertIn("CRITICAL", reasons)

    def test_a_failing_test_also_produces_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_broken.py").write_text(
                "def test_fails():\n    assert 1 == 2\n", encoding="utf-8"
            )
            result = run_audit(root, execute=True, timeout=30)
            self.assertEqual(result["verdict"]["status"], "NOT_READY")

    def test_verdict_always_declares_its_scope_limitation(self):
        """Every verdict must disclose what it does not cover."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(CLEAN_SAMPLE, encoding="utf-8")
            result = run_audit(tmp, execute=True)
            reasons = " ".join(result["verdict"]["reasons"])
            self.assertIn("API/OpenAPI/browser", reasons)


class TestAuditStructure(unittest.TestCase):
    """The result shape and the security check is not run twice."""

    def test_result_is_json_serialisable(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(CLEAN_SAMPLE, encoding="utf-8")
            result = run_audit(tmp, execute=True)
            json.dumps(result)  # raises if not serialisable

    def test_security_check_is_not_duplicated_in_core_checks(self):
        """run-checks.py discovers a 'security' check; run-audit already runs
        that scan directly in section 2, so it must not appear a second time
        in the core-checks list."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(CLEAN_SAMPLE, encoding="utf-8")
            (Path(tmp) / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
            result = run_audit(tmp, execute=False)
            names = [c["name"] for c in result["core_checks"]["checks"]]
            self.assertNotIn("security", names)

    def test_category_filter_is_honoured(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(VULNERABLE_SAMPLE, encoding="utf-8")
            result = run_audit(tmp, execute=False, security_categories=["secrets"])
            categories = {f["category"] for f in result["security"]["findings"]}
            self.assertEqual(categories - {"secrets"}, set())

    def test_catalog_snapshot_reflects_the_real_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_audit(tmp, execute=False)
            self.assertIsNotNone(result["catalog_snapshot"])
            self.assertGreater(result["catalog_snapshot"]["total_cases"], 100)


class TestAuditFormatting(unittest.TestCase):
    """Text and Markdown rendering."""

    def test_text_report_contains_the_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(VULNERABLE_SAMPLE, encoding="utf-8")
            result = run_audit(tmp, execute=True)
            text = format_text_report(result)
            self.assertIn("VERDICT: NOT_READY", text)
            self.assertIn("SEC-INJ-001", text)

    def test_markdown_report_is_well_formed(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(CLEAN_SAMPLE, encoding="utf-8")
            result = run_audit(tmp, execute=True)
            md = format_markdown_report(result)
            self.assertTrue(md.startswith("# Veriflow Full Audit"))
            self.assertIn("## Verdict:", md)
            self.assertIn("## 1. Project", md)
            self.assertIn("## 2. Static Security Scan", md)
            self.assertIn("Safety Notice", md)

    def test_secret_values_never_reach_either_report_format(self):
        secret = "Kf8sLq2mXz9vNb4tRw7p"
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "conf.py").write_text(f'DB_PASSWORD = "{secret}"\n', encoding="utf-8")
            result = run_audit(tmp, execute=False)
            self.assertNotIn(secret, format_text_report(result))
            self.assertNotIn(secret, format_markdown_report(result))
            self.assertNotIn(secret, json.dumps(result))


class TestAuditCli(unittest.TestCase):
    """The command-line contract."""

    def test_json_flag_emits_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(CLEAN_SAMPLE, encoding="utf-8")
            proc = run_cli(tmp, "--execute", "--json")
            data = json.loads(proc.stdout)
            self.assertEqual(data["engine"], "veriflow-audit")

    def test_not_ready_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(VULNERABLE_SAMPLE, encoding="utf-8")
            proc = run_cli(tmp, "--execute")
            self.assertEqual(proc.returncode, 1)

    def test_ready_with_risks_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(CLEAN_SAMPLE, encoding="utf-8")
            proc = run_cli(tmp, "--execute")
            self.assertEqual(proc.returncode, 0)

    def test_markdown_flag_writes_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(CLEAN_SAMPLE, encoding="utf-8")
            out_path = Path(tmp) / "report.md"
            proc = run_cli(tmp, "--execute", "--markdown", str(out_path))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(out_path.is_file())
            self.assertIn("Veriflow Full Audit", out_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

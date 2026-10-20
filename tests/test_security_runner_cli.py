"""
Tests for the security runner CLI and its integration into run-checks.py.

Focus: the CLI contract a user and an agent depend on. Valid JSON, honest exit
codes, preview that genuinely sends nothing, loud failure on a bad filter, and
discovery that reports the static/live split truthfully.
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
SECURITY_CLI = REPO_ROOT / "skills" / "veriflow" / "scripts" / "run-security-tests.py"
FIXTURE_SERVER = REPO_ROOT / "examples" / "security-demo" / "server.py"

_spec = importlib.util.spec_from_file_location("veriflow_security_fixture_cli", FIXTURE_SERVER)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
SecurityFixtureServer = _module.SecurityFixtureServer

VULNERABLE_PROJECT = '''\
import pickle
import subprocess

DB_PASSWORD = "Kf8sLq2mXz9vNb4tRw7p"


def run(name):
    subprocess.run("ls " + name, shell=True)


def load(blob):
    return pickle.loads(blob)
'''

CLEAN_PROJECT = '''\
import json
import os
import subprocess

DB_PASSWORD = os.environ["DB_PASSWORD"]


def run(name):
    subprocess.run(["ls", name], check=True)


def load(blob):
    return json.loads(blob)
'''


def run_cli(*args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    """Invoke the security runner CLI as a user would."""
    return subprocess.run(
        [sys.executable, str(SECURITY_CLI), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class TestStaticScanCli(unittest.TestCase):
    """The static half runs with no prerequisites and no opt-in."""

    def test_clean_project_passes_with_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(CLEAN_PROJECT, encoding="utf-8")
            proc = run_cli(tmp)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_vulnerable_project_fails_with_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(VULNERABLE_PROJECT, encoding="utf-8")
            proc = run_cli(tmp)
            self.assertEqual(proc.returncode, 1)
            for rule in ("SEC-SECRET-001", "SEC-INJ-001", "SEC-DESER-001"):
                with self.subTest(rule=rule):
                    self.assertIn(rule, proc.stdout)

    def test_json_report_is_valid_and_structured(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(VULNERABLE_PROJECT, encoding="utf-8")
            proc = run_cli(tmp, "--json")
            data = json.loads(proc.stdout)
            self.assertEqual(data["engine"], "veriflow-security")
            self.assertIsNotNone(data["static"])
            self.assertIsNone(data["live"], "no --url means no live section")
            self.assertGreater(data["static"]["total_findings"], 0)
            self.assertIn("limitations", data["static"])

    def test_secret_value_is_absent_from_cli_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(VULNERABLE_PROJECT, encoding="utf-8")
            text = run_cli(tmp).stdout
            js = run_cli(tmp, "--json").stdout
            self.assertNotIn("Kf8sLq2mXz9vNb4tRw7p", text)
            self.assertNotIn("Kf8sLq2mXz9vNb4tRw7p", js)

    def test_category_filter_narrows_the_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(VULNERABLE_PROJECT, encoding="utf-8")
            proc = run_cli(tmp, "--category", "secrets", "--json")
            data = json.loads(proc.stdout)
            categories = {f["category"] for f in data["static"]["findings"]}
            self.assertEqual(categories, {"secrets"})

    def test_unknown_category_exits_two_with_the_available_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli(tmp, "--category", "nonsense")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("Unknown security category", proc.stderr)
            self.assertIn("Available:", proc.stderr)

    def test_exclude_flag_removes_files_and_discloses_the_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text(VULNERABLE_PROJECT, encoding="utf-8")
            proc = run_cli(tmp, "--exclude", "app.py", "--json")
            data = json.loads(proc.stdout)["static"]
            self.assertEqual(data["total_findings"], 0)
            self.assertEqual(data["excluded_files"], 1)
            self.assertTrue(
                any("excluded from the scan" in lim for lim in data["limitations"]),
                "an exclusion must be disclosed, not silent",
            )

    def test_no_static_without_url_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli(tmp, "--no-static")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("nothing to do", proc.stderr)


class TestLiveCheckCli(unittest.TestCase):
    """The live half previews by default and requires --execute."""

    def test_preview_is_the_default_and_states_it_sent_nothing(self):
        with SecurityFixtureServer() as server:
            with tempfile.TemporaryDirectory() as tmp:
                proc = run_cli(tmp, "--no-static", "--url", server.base_url)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("Live Security Check Preview", proc.stdout)
            self.assertIn("No HTTP request has been sent", proc.stdout)
            self.assertIn("Pass --execute", proc.stdout)

    def test_preview_json_marks_mode_preview(self):
        with SecurityFixtureServer() as server:
            with tempfile.TemporaryDirectory() as tmp:
                proc = run_cli(tmp, "--no-static", "--url", server.base_url, "--json")
            data = json.loads(proc.stdout)
            self.assertEqual(data["live"]["mode"], "preview")
            self.assertIn("No HTTP request was sent", data["live"]["safety_notice"])
            self.assertTrue(data["live"]["planned_checks"])

    def test_execute_runs_the_checks_against_the_secure_fixture(self):
        with SecurityFixtureServer() as server:
            with tempfile.TemporaryDirectory() as tmp:
                proc = run_cli(
                    tmp,
                    "--no-static",
                    "--url", server.base_url,
                    "--execute",
                    "--protected-path", "/account",
                    "--reflect-path", "/echo",
                    "--error-path", "/boom",
                    "--login-path", "/login",
                    "--state-change-path", "/profile/update",
                    "--redirect-path", "/go",
                    "--user-a-token", "vf-token-user-a",
                    "--user-b-resource", "/records/rec-b",
                    "--json",
                )
            data = json.loads(proc.stdout)
            self.assertEqual(data["live"]["mode"], "executed")
            self.assertEqual(data["live"]["summary"]["FAIL"], 0, data["live"])
            self.assertEqual(data["live"]["summary"]["PASS"], 9)
            self.assertEqual(proc.returncode, 0)

    def test_execute_fails_with_exit_one_on_a_broken_fixture(self):
        with SecurityFixtureServer({"open_protected_route"}) as server:
            with tempfile.TemporaryDirectory() as tmp:
                proc = run_cli(
                    tmp,
                    "--no-static",
                    "--url", server.base_url,
                    "--execute",
                    "--protected-path", "/account",
                    "--check", "SEC-LIVE-AUTH-001",
                    "--json",
                )
            data = json.loads(proc.stdout)
            self.assertEqual(data["live"]["summary"]["FAIL"], 1)
            self.assertEqual(proc.returncode, 1)

    def test_external_url_is_refused_with_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli(tmp, "--no-static", "--url", "http://example.com", "--execute")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("not a local/loopback address", proc.stderr)

    def test_unknown_check_filter_exits_two(self):
        with SecurityFixtureServer() as server:
            with tempfile.TemporaryDirectory() as tmp:
                proc = run_cli(
                    tmp, "--no-static", "--url", server.base_url,
                    "--execute", "--check", "SEC-LIVE-NOPE-001",
                )
            self.assertEqual(proc.returncode, 2)
            self.assertIn("unknown live check id", proc.stderr.lower())

    def test_check_without_url_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli(tmp, "--check", "SEC-LIVE-AUTH-001")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("requires --url", proc.stderr)

    def test_help_documents_the_execute_opt_in(self):
        proc = run_cli("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--execute", proc.stdout)
        self.assertIn("loopback", proc.stdout.lower())


if __name__ == "__main__":
    unittest.main()

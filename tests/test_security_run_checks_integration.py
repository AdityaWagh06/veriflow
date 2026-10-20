"""
Tests that the security phase is discoverable through the unified runner.

A phase nobody can find through `run-checks.py` is a phase nobody will run, so
these tests cover discovery, `--check security` filtering, the honesty of the
static/live split it reports, and that discovery itself executes nothing.
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
RUN_CHECKS = REPO_ROOT / "skills" / "veriflow" / "scripts" / "run-checks.py"

_spec = importlib.util.spec_from_file_location("veriflow_run_checks_sec", RUN_CHECKS)
_run_checks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_run_checks)
discover_checks = _run_checks.discover_checks

SAMPLE_SOURCE = 'import os\n\nAPI_KEY = os.environ["API_KEY"]\n'


class TestSecurityPhaseDiscovery(unittest.TestCase):
    """Discovery behaviour of the security phase."""

    def test_security_check_is_discovered_for_a_source_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(SAMPLE_SOURCE, encoding="utf-8")
            result = discover_checks(tmp)
            names = {c["name"] for c in result["discovered_checks"]}
            self.assertIn("security", names)

    def test_security_check_is_not_proposed_for_an_empty_directory(self):
        """A clean scan over zero files is a vacuous pass, so propose nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            result = discover_checks(tmp)
            names = {c["name"] for c in result["discovered_checks"]}
            self.assertNotIn("security", names)

    def test_security_check_is_not_proposed_for_a_binary_only_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "logo.png").write_bytes(b"\x89PNG\r\n")
            (Path(tmp) / "notes.rtf").write_text("plain", encoding="utf-8")
            result = discover_checks(tmp)
            names = {c["name"] for c in result["discovered_checks"]}
            self.assertNotIn("security", names)

    def test_discovered_security_check_is_not_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(SAMPLE_SOURCE, encoding="utf-8")
            result = discover_checks(tmp)
            check = next(c for c in result["discovered_checks"] if c["name"] == "security")
            self.assertEqual(check["status"], "proposed")
            self.assertFalse(check["executed"])

    def test_security_check_declares_an_argument_list_not_a_shell_string(self):
        """Safe execution depends on argv form, so assert it is a list."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(SAMPLE_SOURCE, encoding="utf-8")
            result = discover_checks(tmp)
            check = next(c for c in result["discovered_checks"] if c["name"] == "security")
            self.assertIsInstance(check["command"], list)
            self.assertGreaterEqual(len(check["command"]), 3)
            self.assertTrue(check["command"][1].endswith("run-security-tests.py"))

    def test_discovery_discloses_that_live_checks_are_opt_in(self):
        """The limitation must say the static scan is not the whole phase."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(SAMPLE_SOURCE, encoding="utf-8")
            result = discover_checks(tmp)
            joined = " ".join(result["limitations"])
            self.assertIn("STATIC scan only", joined)
            self.assertIn("--execute", joined)

    def test_check_filter_selects_only_the_security_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text(SAMPLE_SOURCE, encoding="utf-8")
            (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
            result = discover_checks(tmp, check_name="security")
            names = {c["name"] for c in result["discovered_checks"]}
            self.assertEqual(names, {"security"})


class TestSecurityPhaseExecution(unittest.TestCase):
    """Executing the phase through the unified runner."""

    def test_executing_the_security_check_passes_on_clean_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(SAMPLE_SOURCE, encoding="utf-8")
            result = discover_checks(tmp, execute=True, check_name="security", timeout=180)
            check = result["discovered_checks"][0]
            self.assertTrue(check["executed"])
            self.assertEqual(check["status"], "PASS", check.get("stdout", "")[:600])

    def test_executing_the_security_check_fails_on_vulnerable_source(self):
        vulnerable = 'import pickle\n\n\ndef load(blob):\n    return pickle.loads(blob)\n'
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(vulnerable, encoding="utf-8")
            result = discover_checks(tmp, execute=True, check_name="security", timeout=180)
            check = result["discovered_checks"][0]
            self.assertEqual(check["status"], "FAIL")
            self.assertIn("SEC-DESER-001", check.get("stdout", ""))

    def test_cli_preview_lists_the_security_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text(SAMPLE_SOURCE, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(RUN_CHECKS), tmp, "--json"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            data = json.loads(proc.stdout)
            names = {c["name"] for c in data["discovered_checks"]}
            self.assertIn("security", names)
            self.assertFalse(data["executed"])


if __name__ == "__main__":
    unittest.main()

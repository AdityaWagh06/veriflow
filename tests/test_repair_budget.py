"""
Tests for the repair-attempt budget tracker.

This is the one place Veriflow enforces its 3-attempt cap in code rather than
only in prose: these tests prove the enforcement actually works, is isolated
per issue and per project, survives a corrupted session file, and that the
CLI's exit codes are honest (0 = allowed, 1 = exceeded).
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from skills.veriflow.scripts.repair_budget import (
    MAX_ATTEMPTS,
    InvalidIssueIdError,
    get_status,
    list_sessions,
    record_attempt,
    reset,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "skills" / "veriflow" / "scripts" / "repair_budget.py"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args], capture_output=True, text=True, timeout=30
    )


class TestBudgetAccounting(unittest.TestCase):
    """The core enforcement: exactly 3 allowed, the 4th refused."""

    def test_fresh_issue_has_full_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = get_status(tmp, "issue-a")
            self.assertEqual(status["attempts_used"], 0)
            self.assertEqual(status["attempts_remaining"], MAX_ATTEMPTS)
            self.assertFalse(status["exceeded"])

    def test_three_attempts_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(MAX_ATTEMPTS):
                result = record_attempt(tmp, "issue-a", note=f"attempt {i + 1}")
                with self.subTest(attempt=i + 1):
                    self.assertEqual(result["status"], "ALLOWED")

    def test_the_fourth_attempt_is_exceeded(self):
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(MAX_ATTEMPTS):
                record_attempt(tmp, "issue-a")
            fourth = record_attempt(tmp, "issue-a", note="one too many")
            self.assertEqual(fourth["status"], "EXCEEDED")

    def test_exceeded_state_persists_across_further_calls(self):
        """Budget enforcement must not reset itself just because time passed."""
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(MAX_ATTEMPTS + 2):
                record_attempt(tmp, "issue-a")
            status = get_status(tmp, "issue-a")
            self.assertTrue(status["exceeded"])
            self.assertEqual(status["attempts_remaining"], 0)

    def test_history_records_notes_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_attempt(tmp, "issue-a", note="first")
            record_attempt(tmp, "issue-a", note="second")
            status = get_status(tmp, "issue-a")
            notes = [entry["note"] for entry in status["history"]]
            self.assertEqual(notes, ["first", "second"])


class TestBudgetIsolation(unittest.TestCase):
    """Sessions must not leak across issues or across projects."""

    def test_different_issues_have_independent_budgets(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_attempt(tmp, "issue-a")
            record_attempt(tmp, "issue-a")
            status_a = get_status(tmp, "issue-a")
            status_b = get_status(tmp, "issue-b")
            self.assertEqual(status_a["attempts_used"], 2)
            self.assertEqual(status_b["attempts_used"], 0)

    def test_different_project_roots_have_independent_budgets(self):
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            record_attempt(tmp_a, "shared-issue-name")
            record_attempt(tmp_a, "shared-issue-name")
            record_attempt(tmp_a, "shared-issue-name")
            status_other_project = get_status(tmp_b, "shared-issue-name")
            self.assertEqual(status_other_project["attempts_used"], 0)

    def test_reset_clears_only_the_named_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_attempt(tmp, "issue-a")
            record_attempt(tmp, "issue-b")
            reset(tmp, "issue-a")
            self.assertEqual(get_status(tmp, "issue-a")["attempts_used"], 0)
            self.assertEqual(get_status(tmp, "issue-b")["attempts_used"], 1)

    def test_list_sessions_reports_every_recorded_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_attempt(tmp, "issue-a")
            record_attempt(tmp, "issue-b")
            ids = {s["issue_id"] for s in list_sessions(tmp)}
            self.assertEqual(ids, {"issue-a", "issue-b"})

    def test_list_sessions_on_a_project_with_none_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list_sessions(tmp), [])


class TestBudgetRobustness(unittest.TestCase):
    """A corrupted session file must degrade safely, never crash."""

    def test_corrupted_session_file_is_treated_as_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / ".veriflow" / "repair-sessions"
            session_dir.mkdir(parents=True)
            (session_dir / "issue-a.json").write_text("{ not valid json", encoding="utf-8")

            status = get_status(tmp, "issue-a")
            self.assertEqual(status["attempts_used"], 0)

    def test_invalid_issue_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad_id in ("../escape", "has spaces", "", "semi;colon", "a" * 200):
                with self.subTest(bad_id=bad_id):
                    with self.assertRaises(InvalidIssueIdError):
                        record_attempt(tmp, bad_id)

    def test_session_cannot_escape_the_project_root(self):
        """A path-traversal-shaped issue id must never write outside .veriflow/."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(InvalidIssueIdError):
                record_attempt(tmp, "../../etc/passwd")


class TestBudgetCli(unittest.TestCase):
    """The command-line contract: honest exit codes, valid JSON."""

    def test_attempt_within_budget_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli("--root", tmp, "--attempt", "cli-issue", "--note", "fix")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("1 / 3", proc.stdout)

    def test_exceeding_budget_exits_one_with_refusal_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(MAX_ATTEMPTS):
                run_cli("--root", tmp, "--attempt", "cli-issue")
            proc = run_cli("--root", tmp, "--attempt", "cli-issue")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("REFUSED", proc.stdout)
            self.assertIn("Stop making speculative edits", proc.stdout)

    def test_status_on_exceeded_issue_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(MAX_ATTEMPTS):
                run_cli("--root", tmp, "--attempt", "cli-issue")
            proc = run_cli("--root", tmp, "--status", "cli-issue")
            self.assertEqual(proc.returncode, 1)

    def test_status_within_budget_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_cli("--root", tmp, "--attempt", "cli-issue")
            proc = run_cli("--root", tmp, "--status", "cli-issue")
            self.assertEqual(proc.returncode, 0)

    def test_json_output_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli("--root", tmp, "--attempt", "cli-issue", "--json")
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "ALLOWED")
            self.assertEqual(data["attempts_used"], 1)

    def test_reset_cli_clears_the_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_cli("--root", tmp, "--attempt", "cli-issue")
            proc = run_cli("--root", tmp, "--reset", "cli-issue")
            self.assertEqual(proc.returncode, 0)
            status = get_status(tmp, "cli-issue")
            self.assertEqual(status["attempts_used"], 0)

    def test_invalid_issue_id_via_cli_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli("--root", tmp, "--attempt", "../escape")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("Invalid issue id", proc.stderr)

    def test_mutually_exclusive_actions_are_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli("--root", tmp, "--attempt", "a", "--status", "a")
            self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()

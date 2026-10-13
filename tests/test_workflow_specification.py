"""
Tests for Veriflow workflow documentation and specification integrity.

Verifies that SKILL.md and verification-checklist.md systematically define
the bounded repair lifecycle, attempt limits, failure triage, and reporting requirements.
"""

from __future__ import annotations

from pathlib import Path
import unittest


class TestWorkflowSpecification(unittest.TestCase):
    """Ensure the skill documentation adheres to bounded repair specifications."""

    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).parent.parent
        cls.skill_path = cls.repo_root / "skills" / "veriflow" / "SKILL.md"
        cls.checklist_path = cls.repo_root / "skills" / "veriflow" / "references" / "verification-checklist.md"

        cls.skill_text = cls.skill_path.read_text(encoding="utf-8")
        cls.checklist_text = cls.checklist_path.read_text(encoding="utf-8")

    def test_skill_defines_nine_step_lifecycle(self):
        """Verify SKILL.md documents all 9 lifecycle steps."""
        expected_steps = [
            "Step 1: Discover Project Checks",
            "Step 2: Show Planned Checks (Preview)",
            "Step 3: Execute Only When Explicitly Authorized",
            "Step 4: Collect Results and Structured Diagnostics",
            "Step 5: Analyze Evidence and Identify Root Cause",
            "Step 6: Propose or Apply the Smallest Reasonable Code Change",
            "Step 7: Rerun the Relevant Failing Check",
            "Step 8: Rerun Broader Verification Suite",
            "Step 9: Report Final Results",
        ]
        for step in expected_steps:
            with self.subTest(step=step):
                self.assertIn(step, self.skill_text)

    def test_skill_enforces_three_attempt_limit_and_distinctions(self):
        """Verify SKILL.md enforces the 3-attempt limit and separates diagnosis from repair."""
        self.assertIn("Maximum 3 Repair Attempts", self.skill_text)
        self.assertIn("3 repair attempts", self.skill_text)
        self.assertIn("Diagnosis", self.skill_text)
        self.assertIn("Attempted Repair", self.skill_text)
        self.assertIn("Verified Repair", self.skill_text)
        # Ensure read-only inspection does not count as an attempt
        self.assertIn("Read-only investigation", self.skill_text)
        # Ensure re-verification requirement
        self.assertIn("Immediate Re-Verification", self.skill_text)

    def test_skill_prohibits_anti_patterns(self):
        """Verify strict prohibitions on test deletion, assertion weakening, and rule suppression."""
        self.assertIn("Never delete or weaken tests", self.skill_text)
        self.assertIn("Never disable linter or type-checker rules", self.skill_text)
        self.assertIn("Never suppress errors", self.skill_text)
        self.assertIn("Never alter project configuration arbitrarily", self.skill_text)

    def test_skill_handles_uncertain_and_non_code_failures(self):
        """Verify separate triage for unclassified, missing commands, timeouts, and pre-existing failures."""
        self.assertIn("UNCLASSIFIED", self.skill_text)
        self.assertIn("COMMAND_NOT_FOUND", self.skill_text)
        self.assertIn("TIMEOUT", self.skill_text)
        self.assertIn("Pre-Existing Failures", self.skill_text)
        self.assertIn("Do not guess or hallucinate explanations", self.skill_text)

    def test_skill_separates_runner_and_agent_responsibilities(self):
        """Verify run-checks.py remains a runner while host agent handles edits."""
        self.assertIn("Separation of Runner and Editing Responsibilities", self.skill_text)
        self.assertIn("Verification Runner (`run-checks.py`)", self.skill_text)
        self.assertIn("Host AI Coding Agent", self.skill_text)
        self.assertIn("preview-only by default", self.skill_text)
        self.assertIn("no automatic file modification logic", self.skill_text)

    def test_skill_standardized_report_schema(self):
        """Verify SKILL.md defines the complete standardized completion report schema."""
        expected_sections = [
            "### Changes Summary",
            "### Checks Discovered",
            "### Checks Executed & Statuses",
            "### Diagnosed Failures & Evidence",
            "### Files Changed by Agent",
            "### Repair Attempts",
            "### Checks Rerun After Repairs",
            "### Final Verification Status",
            "### Remaining Risks, Uncertainties & Limitations",
            "### Safety Notice",
            "### Recommended Next Step",
        ]
        for section in expected_sections:
            with self.subTest(section=section):
                self.assertIn(section, self.skill_text)

    def test_verification_checklist_failure_triage_and_reporting(self):
        """Verify verification-checklist.md includes failure triage and updated reporting items."""
        self.assertIn("## 4. Failure Triage and Bounded Repair", self.checklist_text)
        self.assertIn("Track Repair Budget", self.checklist_text)
        self.assertIn("Never Repeat Unsuccessful Fixes", self.checklist_text)
        self.assertIn("Re-Verify Immediately", self.checklist_text)
        self.assertIn("Enforce Code Integrity Prohibitions", self.checklist_text)
        self.assertIn("## 8. Final Report", self.checklist_text)

    def test_skill_documents_check_flag_filtering(self):
        """Verify SKILL.md and checklist document targeted --check filtering."""
        self.assertIn("--check NAME", self.skill_text)
        self.assertIn("--check <failing-check-name>", self.skill_text)
        self.assertIn("--check <name>", self.skill_text)
        self.assertIn("--check <failing-check-name> --execute", self.checklist_text)


if __name__ == "__main__":
    unittest.main()
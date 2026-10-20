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

    #: Reference files SKILL.md delegates detail to. SKILL.md is the Level 2
    #: entry point, budgeted at under 5k tokens by the Agent Skills
    #: documentation, so the nine-step lifecycle, the triage table and the
    #: report templates live in these files. The behavioural rules asserted
    #: below are unchanged; they are checked across the whole skill bundle so
    #: the test verifies the rule exists somewhere the agent will read, rather
    #: than pinning it to one file.
    BUNDLE_FILES = (
        "SKILL.md",
        "references/repair-workflow.md",
        "references/engines.md",
        "references/production-readiness.md",
        "references/report-templates.md",
    )

    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).parent.parent
        cls.skill_dir = cls.repo_root / "skills" / "veriflow"
        cls.skill_path = cls.skill_dir / "SKILL.md"
        cls.checklist_path = cls.skill_dir / "references" / "verification-checklist.md"

        cls.skill_entry_text = cls.skill_path.read_text(encoding="utf-8")
        cls.checklist_text = cls.checklist_path.read_text(encoding="utf-8")

        # The bundle: SKILL.md plus every reference file it delegates to.
        missing = [name for name in cls.BUNDLE_FILES if not (cls.skill_dir / name).is_file()]
        if missing:
            raise AssertionError(f"skill bundle is missing referenced files: {missing}")
        cls.skill_text = chr(10).join(
            (cls.skill_dir / name).read_text(encoding="utf-8") for name in cls.BUNDLE_FILES
        )

    def test_skill_entry_point_stays_within_progressive_disclosure_budget(self):
        """SKILL.md is always loaded, so it must stay small.

        The Agent Skills documentation budgets the SKILL.md body at under 5k
        tokens. Line count is the stable proxy: at roughly 14 tokens per line
        of prose and tables, 300 lines leaves clear headroom.
        """
        line_count = len(self.skill_entry_text.splitlines())
        self.assertLess(
            line_count,
            300,
            f"SKILL.md is {line_count} lines; move detail into a reference file.",
        )

    def test_skill_entry_point_links_every_bundle_reference(self):
        """A reference file nobody is told to read is a file nobody reads."""
        for name in self.BUNDLE_FILES[1:]:
            with self.subTest(reference=name):
                self.assertIn(
                    name.split("/", 1)[1],
                    self.skill_entry_text,
                    f"SKILL.md never points the agent at {name}",
                )

    def test_skill_frontmatter_is_valid_for_claude_code_discovery(self):
        """Claude Code matches a request against the frontmatter description.

        Field constraints come from the Agent Skills documentation: name at most
        64 characters, lowercase letters, digits and hyphens only, and not
        containing a reserved vendor word; description non-empty and at most
        1024 characters.
        """
        newline = chr(10)
        tab = chr(9)
        text = self.skill_entry_text
        self.assertTrue(
            text.startswith("---" + newline), "SKILL.md must open with YAML frontmatter"
        )

        end = text.index(newline + "---", 4)
        frontmatter = text[4:end]

        fields = {}
        current_key = None
        for raw in frontmatter.splitlines():
            if raw and not raw.startswith((" ", tab)) and ":" in raw:
                current_key, _, value = raw.partition(":")
                fields[current_key.strip()] = value.strip()
            elif current_key:
                fields[current_key] += " " + raw.strip()

        self.assertIn("name", fields)
        self.assertIn("description", fields)

        name = fields["name"]
        self.assertEqual(name, "veriflow")
        self.assertLessEqual(len(name), 64)
        self.assertRegex(name, r"^[a-z0-9-]+$")
        for reserved in ("anthropic", "claude"):
            self.assertNotIn(reserved, name.lower())

        description = fields["description"]
        self.assertTrue(description)
        self.assertLessEqual(len(description), 1024)
        self.assertNotIn("<", description, "description must not contain XML tags")
        # The description must say both what it does and when to use it.
        self.assertIn("Use when", description)

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
"""
Tests for the AI-assisted coding failure pattern catalog.

A knowledge base that overstates its own coverage is worse than none, so these
tests check the claims, not just the shape:

  - every pattern carries each schema field, populated
  - enumerated values are declared values
  - a pattern claiming `automated` coverage names a Veriflow check that exists
  - a pattern citing `empirical` evidence cites a reference that records an
    actual figure, and that reference carries a retrieval date
  - citations resolve to declared references (no dangling or invented source)
  - the catalog does not duplicate the same underlying failure
"""

from __future__ import annotations

import json
import re
from pathlib import Path
import unittest

from skills.veriflow.scripts.security_checks import LIVE_CHECKS_BY_ID
from skills.veriflow.scripts.security_scanner import RULES_BY_ID

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCES = REPO_ROOT / "skills" / "veriflow" / "references"
PATTERNS_PATH = REFERENCES / "failure-patterns.json"
DIAGNOSTICS_PATH = REFERENCES / "diagnostics.md"

REQUIRED_FIELDS = (
    "id",
    "title",
    "category",
    "subcategory",
    "symptom",
    "typical_trigger",
    "diagnostic_signatures",
    "root_cause_hypotheses",
    "evidence_to_distinguish",
    "reproduction_strategy",
    "applicable_ecosystems",
    "recommended_checks",
    "safe_repair",
    "regression_tests",
    "severity",
    "confidence_guidance",
    "automation_status",
    "veriflow_coverage",
    "preconditions",
    "known_false_positives",
    "manual_review_required",
    "evidence_basis",
    "source_references",
    "source_notes",
)

LIST_FIELDS = (
    "diagnostic_signatures",
    "root_cause_hypotheses",
    "evidence_to_distinguish",
    "recommended_checks",
    "applicable_ecosystems",
)


class TestFailurePatternSchema(unittest.TestCase):
    """Structure and completeness."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(PATTERNS_PATH.read_text(encoding="utf-8"))
        cls.patterns = cls.catalog["patterns"]
        cls.reference_ids = {r["id"] for r in cls.catalog["references"]}
        cls.evidence_bases = {e["id"] for e in cls.catalog["evidence_bases"]}
        cls.automation_statuses = {a["id"] for a in cls.catalog["automation_statuses"]}
        cls.severities = set(cls.catalog["severity_levels"])

    def test_catalog_declares_its_vocabularies(self):
        for key in (
            "version",
            "name",
            "description",
            "last_reviewed",
            "how_to_use",
            "evidence_bases",
            "automation_statuses",
            "severity_levels",
            "references",
            "patterns",
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.catalog)

    def test_last_reviewed_is_an_iso_date(self):
        self.assertRegex(self.catalog["last_reviewed"], r"^\d{4}-\d{2}-\d{2}$")

    def test_every_pattern_has_every_required_field(self):
        for pattern in self.patterns:
            for field in REQUIRED_FIELDS:
                with self.subTest(pattern=pattern.get("id"), field=field):
                    self.assertIn(field, pattern)

    def test_no_required_field_is_empty(self):
        """A present-but-blank field is an unfilled template, not a pattern."""
        for pattern in self.patterns:
            for field in REQUIRED_FIELDS:
                if field in ("source_references", "manual_review_required", "preconditions"):
                    # source_references is empty for an unsourced pattern,
                    # manual_review_required is a boolean, and preconditions is
                    # legitimately empty for a check with no prerequisite at all
                    # (the static secret scan needs nothing installed).
                    continue
                with self.subTest(pattern=pattern["id"], field=field):
                    value = pattern[field]
                    self.assertTrue(value, f"{pattern['id']}.{field} is empty")

    def test_list_fields_are_populated_lists(self):
        for pattern in self.patterns:
            for field in LIST_FIELDS:
                with self.subTest(pattern=pattern["id"], field=field):
                    self.assertIsInstance(pattern[field], list)
                    self.assertGreater(len(pattern[field]), 0)

    def test_ids_are_unique_and_well_formed(self):
        ids = [p["id"] for p in self.patterns]
        self.assertEqual(len(ids), len(set(ids)), "pattern ids must be unique")
        for pattern_id in ids:
            with self.subTest(pattern=pattern_id):
                self.assertRegex(pattern_id, r"^VFP-[A-Z]+-\d{3}$")

    def test_enumerated_values_are_declared(self):
        for pattern in self.patterns:
            with self.subTest(pattern=pattern["id"]):
                self.assertIn(pattern["severity"], self.severities)
                self.assertIn(pattern["automation_status"], self.automation_statuses)
                self.assertIn(pattern["evidence_basis"], self.evidence_bases)
                self.assertIsInstance(pattern["manual_review_required"], bool)

    def test_narrative_fields_are_substantive(self):
        """A one-word 'symptom' helps nobody diagnose anything."""
        for pattern in self.patterns:
            for field in ("symptom", "typical_trigger", "safe_repair", "confidence_guidance", "veriflow_coverage"):
                with self.subTest(pattern=pattern["id"], field=field):
                    self.assertGreater(
                        len(pattern[field]),
                        40,
                        f"{pattern['id']}.{field} is too short to be useful",
                    )

    def test_multiple_root_cause_hypotheses_per_pattern(self):
        """One hypothesis is a conclusion. Diagnosis needs competing explanations."""
        for pattern in self.patterns:
            with self.subTest(pattern=pattern["id"]):
                self.assertGreaterEqual(
                    len(pattern["root_cause_hypotheses"]),
                    3,
                    f"{pattern['id']} offers too few competing explanations",
                )


class TestEvidenceHonesty(unittest.TestCase):
    """The claims about sources and coverage must hold up."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(PATTERNS_PATH.read_text(encoding="utf-8"))
        cls.patterns = cls.catalog["patterns"]
        cls.references = {r["id"]: r for r in cls.catalog["references"]}

    def test_every_citation_resolves_to_a_declared_reference(self):
        """A dangling citation is indistinguishable from an invented one."""
        for pattern in self.patterns:
            for ref_id in pattern["source_references"]:
                with self.subTest(pattern=pattern["id"], reference=ref_id):
                    self.assertIn(ref_id, self.references)

    def test_every_reference_records_url_retrieval_date_and_scope(self):
        for ref_id, ref in self.references.items():
            with self.subTest(reference=ref_id):
                self.assertTrue(ref["url"].startswith("https://"))
                self.assertRegex(ref["retrieved"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertGreater(
                    len(ref["what_it_supports"]),
                    60,
                    f"{ref_id} must state what the source actually supports",
                )

    def test_empirical_patterns_cite_a_reference_carrying_a_figure(self):
        """'empirical' is a strong claim: it needs a number and a sample size."""
        for pattern in self.patterns:
            if pattern["evidence_basis"] != "empirical":
                continue
            with self.subTest(pattern=pattern["id"]):
                self.assertTrue(
                    pattern["source_references"],
                    f"{pattern['id']} claims empirical evidence but cites nothing",
                )
                supporting = " ".join(
                    self.references[r]["what_it_supports"] for r in pattern["source_references"]
                )
                self.assertRegex(
                    supporting,
                    r"\d+(\.\d+)?%",
                    f"{pattern['id']} claims empirical evidence but no cited source records a percentage",
                )
                self.assertRegex(
                    supporting,
                    r"n\s*=\s*[\d,]+",
                    f"{pattern['id']} claims empirical evidence but no cited source records a sample size",
                )
                # And the pattern must quote the figure itself, not just gesture at it.
                self.assertRegex(
                    pattern["source_notes"],
                    r"\d+(\.\d+)?%",
                    f"{pattern['id']} must quote the figure in source_notes",
                )

    def test_practitioner_patterns_claim_no_prevalence(self):
        """Without a study, the pattern must say the frequency is unknown."""
        for pattern in self.patterns:
            if pattern["evidence_basis"] != "practitioner_pattern":
                continue
            with self.subTest(pattern=pattern["id"]):
                self.assertNotRegex(
                    pattern["source_notes"],
                    r"\d+(\.\d+)?%",
                    f"{pattern['id']} is a practitioner pattern but quotes a percentage",
                )
                self.assertIn(
                    "no prevalence figure is claimed",
                    pattern["source_notes"].lower(),
                    f"{pattern['id']} must state that no prevalence figure is claimed",
                )

    def test_automated_patterns_name_an_existing_veriflow_check(self):
        """'automated' must point at something that actually exists."""
        known_checks = set(RULES_BY_ID) | set(LIVE_CHECKS_BY_ID)
        runner_scripts = {
            "run-checks.py",
            "run-security-tests.py",
            "run-api-tests.py",
            "run-openapi-tests.py",
            "run-browser-tests.py",
            "detect-project.py",
        }
        for pattern in self.patterns:
            if pattern["automation_status"] not in ("automated", "partially_automated"):
                continue
            with self.subTest(pattern=pattern["id"]):
                text = pattern["veriflow_coverage"] + " " + " ".join(pattern["recommended_checks"])
                referenced_ids = set(re.findall(r"\bSEC-[A-Z]+-\d+\b", text))
                mentions_runner = any(script in text for script in runner_scripts)
                mentions_structural = "structural" in pattern["veriflow_coverage"].lower()

                self.assertTrue(
                    referenced_ids or mentions_runner or mentions_structural,
                    f"{pattern['id']} claims automation but names no check, runner or structural control",
                )
                for check_id in referenced_ids:
                    self.assertIn(
                        check_id,
                        known_checks,
                        f"{pattern['id']} cites {check_id}, which does not exist",
                    )

    def test_manual_patterns_do_not_claim_veriflow_detects_them(self):
        """A manual_review pattern must say plainly that nothing automated covers it."""
        for pattern in self.patterns:
            if pattern["automation_status"] != "manual_review":
                continue
            with self.subTest(pattern=pattern["id"]):
                coverage = pattern["veriflow_coverage"].lower()
                self.assertTrue(
                    coverage.startswith("none") or "does not" in coverage or "cannot" in coverage,
                    f"{pattern['id']} is manual_review but its coverage text does not say so",
                )

    def test_every_pattern_declares_known_false_positives(self):
        """A detection claim without a false-positive statement is overclaiming."""
        for pattern in self.patterns:
            with self.subTest(pattern=pattern["id"]):
                self.assertGreater(len(pattern["known_false_positives"]), 20)

    def test_manual_review_flag_agrees_with_automation_status(self):
        for pattern in self.patterns:
            if pattern["automation_status"] == "manual_review":
                with self.subTest(pattern=pattern["id"]):
                    self.assertTrue(
                        pattern["manual_review_required"],
                        f"{pattern['id']} is manual_review but manual_review_required is False",
                    )


class TestCatalogCoverageAndGrouping(unittest.TestCase):
    """Breadth without duplication."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(PATTERNS_PATH.read_text(encoding="utf-8"))
        cls.patterns = cls.catalog["patterns"]

    def test_the_mandated_categories_are_covered(self):
        categories = {p["category"] for p in self.patterns}
        for required in (
            "general_correctness",
            "dependency_and_environment",
            "tests_and_debugging",
            "web_frontend",
            "backend_and_apis",
            "databases_and_persistence",
            "security",
            "ai_agent_workflow",
        ):
            with self.subTest(category=required):
                self.assertIn(required, categories)

    def test_no_two_patterns_share_a_title(self):
        titles = [p["title"] for p in self.patterns]
        self.assertEqual(len(titles), len(set(titles)))

    def test_no_two_patterns_share_a_category_and_subcategory_and_symptom(self):
        """Variants of one failure belong in one pattern, not several entries."""
        seen = {}
        for pattern in self.patterns:
            key = (pattern["category"], pattern["subcategory"], pattern["symptom"][:60])
            with self.subTest(pattern=pattern["id"]):
                self.assertNotIn(
                    key,
                    seen,
                    f"{pattern['id']} duplicates {seen.get(key)}; group variants into one pattern",
                )
            seen[key] = pattern["id"]

    def test_ai_agent_workflow_covers_the_owasp_risks_veriflow_addresses(self):
        agent = [p for p in self.patterns if p["category"] == "ai_agent_workflow"]
        self.assertGreaterEqual(len(agent), 4)
        subcategories = {p["subcategory"] for p in agent}
        for required in ("scope", "verification_discipline", "prompt_injection", "reporting"):
            with self.subTest(subcategory=required):
                self.assertIn(required, subcategories)

    def test_critical_patterns_have_a_regression_test_strategy(self):
        for pattern in self.patterns:
            if pattern["severity"] != "CRITICAL":
                continue
            with self.subTest(pattern=pattern["id"]):
                self.assertGreater(len(pattern["regression_tests"]), 30)


class TestDiagnosticsReference(unittest.TestCase):
    """The prose diagnostics reference must be present and linked."""

    @classmethod
    def setUpClass(cls):
        cls.text = DIAGNOSTICS_PATH.read_text(encoding="utf-8")
        cls.skill_text = (REPO_ROOT / "skills" / "veriflow" / "SKILL.md").read_text(encoding="utf-8")

    def test_skill_points_at_both_new_references(self):
        self.assertIn("diagnostics.md", self.skill_text)
        self.assertIn("failure-patterns.json", self.skill_text)

    def test_covers_the_mandated_diagnostic_families(self):
        for topic in (
            "SyntaxError",
            "NameError",
            "ModuleNotFoundError",
            "ImportError",
            "KeyError",
            "IndexError",
            "PermissionError",
            "FileNotFoundError",
            "circular import",
            "Hydration mismatch",
            "Unhandled promise rejection",
            "CORS",
            "Deadlock",
            "Connection pool exhausted",
            "Docker",
        ):
            with self.subTest(topic=topic):
                self.assertIn(topic, self.text)

    def test_covers_the_mandated_http_status_codes(self):
        for status in ("400", "401", "403", "404", "405", "409", "413", "415", "422", "429", "500", "502", "503", "504"):
            with self.subTest(status=status):
                self.assertIn(status, self.text)

    def test_states_that_an_error_message_is_not_a_diagnosis(self):
        """The whole point of the reference, and the easiest thing to omit."""
        self.assertIn("not a diagnosis", self.text)
        self.assertIn("Different cause, same symptom", self.text)

    def test_documents_veriflow_own_diagnostic_states(self):
        for state in ("UNCLASSIFIED", "COMMAND_NOT_FOUND", "TIMEOUT", "BLOCKED"):
            with self.subTest(state=state):
                self.assertIn(state, self.text)

    def test_instructs_reporting_unknown_rather_than_guessing(self):
        self.assertIn("Do not guess", self.text)
        self.assertIn("UNKNOWN", self.text)

    def test_covers_pre_existing_failures(self):
        self.assertIn("Pre-existing failures", self.text)


if __name__ == "__main__":
    unittest.main()

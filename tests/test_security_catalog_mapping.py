"""
Tests that the security mapping index tells the truth.

A mapping file is a coverage claim, and an unchecked coverage claim is how a
verification tool starts lying. These tests assert that every mapped rule and
check actually exists, that every catalog id it references is real, that every
mapping declares a limitation, and that anything claiming `automated` coverage
names a fault test that exists.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from skills.veriflow.scripts.security_checks import LIVE_CHECKS_BY_ID
from skills.veriflow.scripts.security_scanner import RULES_BY_ID

REPO_ROOT = Path(__file__).resolve().parent.parent
MAPPING_PATH = REPO_ROOT / "skills" / "veriflow" / "references" / "security-test-mapping.json"
CATALOG_PATH = REPO_ROOT / "skills" / "veriflow" / "references" / "production-test-catalog.json"


class TestSecurityMappingIntegrity(unittest.TestCase):
    """Structure and referential integrity of the mapping index."""

    @classmethod
    def setUpClass(cls):
        cls.mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.catalog_ids = {case["id"] for case in cls.catalog["test_cases"]}
        cls.coverage_levels = {level["id"] for level in cls.mapping["coverage_levels"]}
        cls.static = cls.mapping["static_mappings"]
        cls.live = cls.mapping["live_mappings"]

    def test_mapping_file_is_valid_json_with_expected_sections(self):
        for key in (
            "version",
            "description",
            "engine",
            "coverage_levels",
            "supported_categories",
            "static_mappings",
            "live_mappings",
            "explicitly_not_covered",
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.mapping)

    def test_every_mapped_static_rule_exists(self):
        """A mapping to a rule that does not exist is a false coverage claim."""
        for entry in self.static:
            with self.subTest(rule=entry["rule_id"]):
                self.assertIn(entry["rule_id"], RULES_BY_ID)

    def test_every_mapped_live_check_exists(self):
        for entry in self.live:
            with self.subTest(check=entry["check_id"]):
                self.assertIn(entry["check_id"], LIVE_CHECKS_BY_ID)

    def test_mapped_severity_and_confidence_match_the_rule(self):
        """The mapping must not overstate a rule's severity or confidence."""
        for entry in self.static:
            rule = RULES_BY_ID[entry["rule_id"]]
            with self.subTest(rule=entry["rule_id"]):
                self.assertEqual(entry["severity"], rule.severity)
                self.assertEqual(entry["confidence"], rule.confidence)

    def test_mapped_rule_claims_a_catalog_id_the_rule_declares(self):
        """A mapping may not attach a rule to a catalog case the rule disowns."""
        for entry in self.static:
            rule = RULES_BY_ID[entry["rule_id"]]
            with self.subTest(rule=entry["rule_id"], catalog=entry["catalog_id"]):
                self.assertIn(
                    entry["catalog_id"],
                    rule.catalog_ids,
                    f"{entry['rule_id']} does not declare {entry['catalog_id']}",
                )

    def test_every_rule_is_mapped(self):
        """An unmapped rule is coverage the catalog cannot see."""
        mapped = {entry["rule_id"] for entry in self.static}
        self.assertEqual(
            set(RULES_BY_ID) - mapped,
            set(),
            "every scanner rule must appear in the mapping index",
        )

    def test_every_live_check_is_mapped(self):
        mapped = {entry["check_id"] for entry in self.live}
        self.assertEqual(set(LIVE_CHECKS_BY_ID) - mapped, set())

    def test_coverage_levels_are_declared_values(self):
        for entry in self.static + self.live:
            key = entry.get("rule_id") or entry.get("check_id")
            with self.subTest(entry=key):
                self.assertIn(entry["coverage"], self.coverage_levels)

    def test_every_mapping_declares_a_limitation(self):
        """Stating what a check does not cover is what keeps the claim honest."""
        for entry in self.static + self.live:
            key = entry.get("rule_id") or entry.get("check_id")
            with self.subTest(entry=key):
                self.assertTrue(entry.get("limitation"), f"{key} declares no limitation")
                self.assertGreater(len(entry["limitation"]), 20)

    def test_every_mapping_names_an_existing_fault_test(self):
        """`automated` coverage requires a real test proving the check fails on a defect."""
        for entry in self.static + self.live:
            key = entry.get("rule_id") or entry.get("check_id")
            with self.subTest(entry=key):
                fault_test = entry.get("fault_test", "")
                self.assertTrue(fault_test, f"{key} names no fault test")
                test_file = fault_test.split("::")[0]
                self.assertTrue(
                    (REPO_ROOT / test_file).is_file(),
                    f"{key} names a fault test file that does not exist: {test_file}",
                )

    def test_live_mappings_name_a_real_fault_mode(self):
        """A mapped fault mode must exist in the fixture, or it was never proven."""
        import importlib.util

        fixture = REPO_ROOT / "examples" / "security-demo" / "server.py"
        spec = importlib.util.spec_from_file_location("veriflow_fixture_check", fixture)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for entry in self.live:
            with self.subTest(check=entry["check_id"]):
                self.assertIn(entry["fault_mode"], module.FAULT_MODES)

    def test_referenced_catalog_ids_exist_or_are_new_security_ids(self):
        """A catalog id must either exist in the catalog or be a documented new one.

        The security phase introduced SEC-017/018/019 (prompt injection, unicode
        injection, install hooks) which predate no catalog entry. They are
        listed here so an accidental typo in an existing id still fails.
        """
        new_security_ids = {"SEC-017", "SEC-018", "SEC-019", "SEC-020"}
        referenced = {entry["catalog_id"] for entry in self.static + self.live}
        for entry in self.mapping["explicitly_not_covered"]:
            referenced.update(entry["catalog_ids"])

        unknown = sorted(referenced - self.catalog_ids - new_security_ids)
        self.assertEqual(
            unknown,
            [],
            f"mapping references catalog ids that do not exist and are not documented as new: {unknown}",
        )

    def test_explicitly_not_covered_sections_have_reasons(self):
        """Declaring a gap is only useful if it says why."""
        self.assertGreaterEqual(len(self.mapping["explicitly_not_covered"]), 3)
        for entry in self.mapping["explicitly_not_covered"]:
            with self.subTest(area=entry["area"]):
                self.assertTrue(entry["area"])
                self.assertGreater(len(entry["reason"]), 40)

    def test_dependency_auditing_is_declared_out_of_scope(self):
        """Veriflow must not imply it performs CVE auditing."""
        areas = " ".join(e["area"] + " " + e["reason"] for e in self.mapping["explicitly_not_covered"])
        self.assertIn("pip-audit", areas)
        self.assertIn("vulnerability database", areas)

    def test_penetration_testing_is_declared_out_of_scope(self):
        areas = " ".join(e["area"] for e in self.mapping["explicitly_not_covered"]).lower()
        self.assertIn("penetration testing", areas)


if __name__ == "__main__":
    unittest.main()

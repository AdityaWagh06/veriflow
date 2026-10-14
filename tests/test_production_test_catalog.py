"""
Tests for Veriflow Production-Readiness Test Catalog.

Validates catalog JSON schema, ID uniqueness, required fields,
category coverage, enumeration integrity, and minimum count thresholds.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest


class TestProductionTestCatalog(unittest.TestCase):
    """Ensure production-test-catalog.json adheres to schema and coverage requirements."""

    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).parent.parent
        cls.catalog_path = cls.repo_root / "skills" / "veriflow" / "references" / "production-test-catalog.json"
        cls.guide_path = cls.repo_root / "skills" / "veriflow" / "references" / "production-test-catalog-guide.md"

        cls.assertTrue(cls.catalog_path.is_file(), f"Catalog not found at {cls.catalog_path}")
        with open(cls.catalog_path, "r", encoding="utf-8") as f:
            cls.catalog = json.load(f)

        cls.test_cases = cls.catalog.get("test_cases", [])

    def test_catalog_file_exists_and_parses_json(self):
        """Verify the catalog file exists and parses as valid JSON."""
        self.assertTrue(self.catalog_path.is_file())
        self.assertIsInstance(self.catalog, dict)
        self.assertTrue(self.guide_path.is_file(), "Catalog guide markdown file must exist")

    def test_catalog_top_level_schema(self):
        """Verify top-level metadata keys exist."""
        required_keys = [
            "$schema",
            "version",
            "name",
            "description",
            "references",
            "categories",
            "result_states",
            "severity_levels",
            "automation_statuses",
            "execution_phases",
            "summary",
            "test_cases",
        ]
        for key in required_keys:
            with self.subTest(key=key):
                self.assertIn(key, self.catalog)

    def test_all_fifteen_categories_defined(self):
        """Verify all 15 required categories are defined."""
        expected_categories = [
            "authentication_and_account_flows",
            "routing_and_navigation",
            "forms_and_input_handling",
            "core_business_logic_and_data_integrity",
            "user_roles_and_authorization",
            "api_and_integration_reliability",
            "ui_quality_and_user_experience",
            "accessibility",
            "security",
            "performance_and_scalability",
            "resilience_and_reliability",
            "deployment_and_production_configuration",
            "search_metadata_and_discoverability",
            "browser_compatibility_and_network_behavior",
            "observability_and_post_deployment_verification",
        ]
        category_ids = [cat["id"] for cat in self.catalog.get("categories", [])]
        self.assertEqual(len(category_ids), 15)
        for cat in expected_categories:
            with self.subTest(category=cat):
                self.assertIn(cat, category_ids)

    def test_total_test_case_minimum_threshold(self):
        """Verify the catalog contains at least 120 distinct test cases."""
        self.assertGreaterEqual(len(self.test_cases), 120)

    def test_unique_stable_ids(self):
        """Verify all test case IDs are unique, non-empty, and follow prefix conventions."""
        seen_ids = set()
        valid_prefixes = (
            "AUTH-", "ROUTE-", "FORM-", "DATA-", "ROLE-",
            "API-", "UIUX-", "A11Y-", "SEC-", "PERF-",
            "RESL-", "CONF-", "SEO-", "NETW-", "OBSV-"
        )
        for tc in self.test_cases:
            tid = tc.get("id")
            self.assertIsInstance(tid, str)
            self.assertTrue(tid.strip())
            self.assertNotIn(tid, seen_ids, f"Duplicate test ID: {tid}")
            seen_ids.add(tid)
            self.assertTrue(
                tid.startswith(valid_prefixes),
                f"Test ID '{tid}' does not start with a recognized prefix"
            )

    def test_test_case_required_fields(self):
        """Verify each test case contains all 16 mandatory schema fields."""
        required_fields = [
            "id",
            "category",
            "subcategory",
            "name",
            "defect_target",
            "applicability_rules",
            "severity",
            "preconditions",
            "steps",
            "expected_result",
            "recommended_automation_method",
            "automation_status",
            "evidence_required",
            "execution_phase",
            "safety_constraints",
            "citations",
        ]
        for tc in self.test_cases:
            tid = tc.get("id", "unknown")
            for field in required_fields:
                with self.subTest(test_id=tid, field=field):
                    self.assertIn(field, tc, f"Test {tid} missing field: {field}")

    def test_valid_enumerations(self):
        """Verify severity, automation_status, and execution_phase use valid enum values."""
        valid_severities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        valid_automation_statuses = {"automated_available", "app_specific_automation", "manual_review"}
        valid_execution_phases = {"pre_deployment", "post_deployment", "both"}

        for tc in self.test_cases:
            tid = tc.get("id")
            with self.subTest(test_id=tid):
                self.assertIn(tc.get("severity"), valid_severities)
                self.assertIn(tc.get("automation_status"), valid_automation_statuses)
                self.assertIn(tc.get("execution_phase"), valid_execution_phases)

    def test_non_empty_lists_and_applicability(self):
        """Verify steps, evidence, preconditions, citations, and applicability rules are populated."""
        for tc in self.test_cases:
            tid = tc.get("id")
            with self.subTest(test_id=tid):
                self.assertIsInstance(tc.get("preconditions"), list)
                self.assertGreater(len(tc["preconditions"]), 0)

                self.assertIsInstance(tc.get("steps"), list)
                self.assertGreater(len(tc["steps"]), 0)

                self.assertIsInstance(tc.get("evidence_required"), list)
                self.assertGreater(len(tc["evidence_required"]), 0)

                self.assertIsInstance(tc.get("citations"), list)
                self.assertGreater(len(tc["citations"]), 0)

                self.assertIsInstance(tc.get("applicability_rules"), dict)
                self.assertGreater(len(tc["applicability_rules"]), 0)

                self.assertIsInstance(tc.get("safety_constraints"), str)
                self.assertTrue(tc["safety_constraints"].strip())

    def test_summary_count_parity(self):
        """Verify summary block numbers accurately match test case list counts."""
        summary = self.catalog.get("summary", {})
        self.assertEqual(summary.get("total_test_cases"), len(self.test_cases))

        by_cat = summary.get("by_category", {})
        for cat_id, count in by_cat.items():
            actual = sum(1 for t in self.test_cases if t["category"] == cat_id)
            self.assertEqual(count, actual, f"Category count mismatch for {cat_id}")

        by_sev = summary.get("by_severity", {})
        for sev, count in by_sev.items():
            actual = sum(1 for t in self.test_cases if t["severity"] == sev)
            self.assertEqual(count, actual, f"Severity count mismatch for {sev}")

    def test_grounding_references_present(self):
        """Verify key technical reference sources are cited in the catalog."""
        refs = self.catalog.get("references", [])
        ref_names = [r["name"] for r in refs]
        expected_refs = [
            "OWASP Authentication Cheat Sheet",
            "OWASP Session Management Cheat Sheet",
            "OWASP Authorization Cheat Sheet",
            "OWASP Web Security Testing Guide",
            "Playwright Authentication Testing Guide",
            "Playwright Network Testing Guide",
            "Google web.dev Core Web Vitals",
            "Google SRE Launch Checklist",
        ]
        for expected in expected_refs:
            with self.subTest(reference=expected):
                self.assertTrue(
                    any(expected in r for r in ref_names),
                    f"Missing expected reference: {expected}"
                )


if __name__ == "__main__":
    unittest.main()

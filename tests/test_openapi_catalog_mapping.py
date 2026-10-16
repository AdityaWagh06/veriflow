"""
Unit tests validating openapi-test-mapping.json against production-test-catalog.json.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest


class TestOpenApiCatalogMapping(unittest.TestCase):
    """Test mapping index structure, schema validity, and catalog cross-references."""

    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.mapping_file = cls.repo_root / "skills" / "veriflow" / "references" / "openapi-test-mapping.json"
        cls.catalog_file = cls.repo_root / "skills" / "veriflow" / "references" / "production-test-catalog.json"

        with open(cls.mapping_file, "r", encoding="utf-8") as f:
            cls.mapping_data = json.load(f)

        with open(cls.catalog_file, "r", encoding="utf-8") as f:
            cls.catalog_data = json.load(f)

    def test_mapping_file_schema_and_metadata(self):
        self.assertIn("version", self.mapping_data)
        self.assertEqual(self.mapping_data["engine"], "openapi_contract")
        self.assertIn("mappings", self.mapping_data)
        self.assertIsInstance(self.mapping_data["mappings"], list)
        self.assertGreaterEqual(len(self.mapping_data["mappings"]), 5)

    def test_all_mapped_ids_exist_in_catalog(self):
        catalog_ids = {case["id"] for case in self.catalog_data["test_cases"]}

        for m in self.mapping_data["mappings"]:
            cid = m["catalog_id"]
            self.assertIn(
                cid,
                catalog_ids,
                f"Mapped catalog_id '{cid}' in openapi-test-mapping.json does not exist in production-test-catalog.json",
            )
            self.assertTrue(m["name"])
            self.assertIn(m["category"], self.mapping_data["supported_categories"])
            self.assertIn(m["verification_scope"], ("live_endpoint", "static_spec"))
            self.assertIn(m["check_type"], ("SPEC_VALIDATION", "ENDPOINT_CONTRACT", "AUTH_ENFORCEMENT", "NEGATIVE_INPUT"))


if __name__ == "__main__":
    unittest.main()

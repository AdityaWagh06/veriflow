"""
Unit tests for the catalog-to-API automation mapping index.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.api_checks import (
    CHECK_FUNCTIONS,
    run_catalog_api_test,
)


class TestApiCatalogMapping(unittest.TestCase):
    """Verify API catalog mapping schema integrity, ID parity, and dispatcher execution."""

    @classmethod
    def setUpClass(cls):
        repo_root = Path(__file__).parent.parent
        catalog_path = repo_root / "skills" / "veriflow" / "references" / "production-test-catalog.json"
        mapping_path = repo_root / "skills" / "veriflow" / "references" / "api-test-mapping.json"

        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog_data = json.load(f)
        with open(mapping_path, "r", encoding="utf-8") as f:
            cls.mapping_data = json.load(f)

        cls.catalog_ids = {case["id"] for case in catalog_data.get("test_cases", [])}
        cls.server = DemoServer(port=0)
        cls.base_url = cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_mapping_schema_fields(self):
        self.assertEqual(self.mapping_data.get("version"), "1.0.0")
        self.assertEqual(self.mapping_data.get("engine"), "python_http")
        self.assertIn("mappings", self.mapping_data)
        mappings = self.mapping_data["mappings"]
        self.assertGreaterEqual(len(mappings), 10)

        for m in mappings:
            cid = m["catalog_id"]
            with self.subTest(catalog_id=cid):
                self.assertIn(cid, self.catalog_ids, f"Mapped catalog_id {cid} not found in production-test-catalog.json")
                self.assertIn("category", m)
                self.assertIn("check_function", m)
                self.assertIn("endpoint", m)
                self.assertIn("method", m)
                self.assertIn(cid, CHECK_FUNCTIONS, f"check_function for {cid} not in CHECK_FUNCTIONS registry")

    def test_dispatch_all_mapped_catalog_checks_pass_clean(self):
        mappings = self.mapping_data["mappings"]
        for m in mappings:
            cid = m["catalog_id"]
            with self.subTest(catalog_id=cid):
                result = run_catalog_api_test(cid, self.base_url)
                self.assertEqual(
                    result.status,
                    "PASS",
                    f"Check {cid} failed unexpectedly: {result.error_message} (evidence: {result.evidence})",
                )


if __name__ == "__main__":
    unittest.main()

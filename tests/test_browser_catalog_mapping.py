"""
Automated unit tests for catalog-to-browser automation mappings.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.browser_detector import detect_browser_environment
from skills.veriflow.scripts.browser_journeys import (
    get_browser_catalog_mappings,
    launch_browser_context,
    run_catalog_browser_test,
)


class TestBrowserCatalogMapping(unittest.TestCase):
    """Verify catalog mapping integrity, schema completeness, and dispatcher execution."""

    @classmethod
    def setUpClass(cls):
        repo_root = Path(__file__).parent.parent
        catalog_path = repo_root / "skills" / "veriflow" / "references" / "production-test-catalog.json"
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog_data = json.load(f)
        cls.catalog_ids = {case["id"] for case in catalog_data.get("test_cases", [])}

        cls.env = detect_browser_environment(probe_launch=False)

    def test_all_mapped_ids_exist_in_production_catalog(self):
        mappings = get_browser_catalog_mappings()
        self.assertGreaterEqual(len(mappings), 15)

        for m in mappings:
            cid = m["catalog_id"]
            with self.subTest(catalog_id=cid):
                self.assertIn(cid, self.catalog_ids, f"Mapped catalog_id {cid} not found in production-test-catalog.json")
                self.assertIn("journey_function", m)
                self.assertIn("category", m)

    def test_unmapped_catalog_id_returns_not_applicable(self):
        result = run_catalog_browser_test("UNMAPPED-999", None, "http://localhost:8080")
        self.assertEqual(result.status, "NOT_APPLICABLE")
        self.assertEqual(result.test_id, "UNMAPPED-999")

    def test_dispatch_by_catalog_id_executes_test(self):
        if not self.env.playwright_installed or not self.env.available_channels:
            raise unittest.SkipTest(f"Browser automation not available: {self.env.reason}")

        server = DemoServer(port=0)
        base_url = server.start()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser, context = launch_browser_context(pw)
            page = context.new_page()
            try:
                # Dispatch AUTH-006 (password toggle)
                result = run_catalog_browser_test("AUTH-006", page, base_url)
                self.assertEqual(result.status, "PASS")
                self.assertEqual(result.test_id, "AUTH-006")
            finally:
                page.close()
                browser.close()
                server.stop()


if __name__ == "__main__":
    unittest.main()

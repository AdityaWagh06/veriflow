"""
Tests for the Claude Code plugin marketplace manifest.

.claude-plugin/marketplace.json is what makes `claude plugin marketplace add
<owner>/veriflow` followed by `claude plugin install veriflow@veriflow` work
with zero file-copying: the plugin entry's `skills` field points straight at
the existing `skills/veriflow` source directory. These tests exist because a
typo or a moved file here breaks that one-command install silently -- Claude
Code's own validation only happens when someone actually runs the command.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"


class TestMarketplaceManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_is_valid_json_at_the_required_path(self):
        """Claude Code only looks at exactly this path, nowhere else."""
        self.assertTrue(MANIFEST_PATH.is_file())

    def test_top_level_required_fields_present(self):
        for field in ("name", "owner", "plugins"):
            with self.subTest(field=field):
                self.assertIn(field, self.manifest)

    def test_owner_has_a_name(self):
        self.assertIn("name", self.manifest["owner"])
        self.assertTrue(self.manifest["owner"]["name"])

    def test_exactly_one_plugin_is_declared(self):
        """This repo is both the marketplace and the one plugin it offers,
        same shape as other single-skill plugin repos."""
        self.assertEqual(len(self.manifest["plugins"]), 1)

    def test_plugin_entry_has_required_fields(self):
        plugin = self.manifest["plugins"][0]
        for field in ("name", "source"):
            with self.subTest(field=field):
                self.assertIn(field, plugin)
                self.assertTrue(plugin[field])

    def test_plugin_name_is_veriflow(self):
        """Determines the install command: `claude plugin install veriflow@veriflow`."""
        self.assertEqual(self.manifest["plugins"][0]["name"], "veriflow")

    def test_plugin_source_is_the_repo_root(self):
        """A relative path starting with ./, per the marketplace source spec."""
        self.assertEqual(self.manifest["plugins"][0]["source"], "./")

    def test_plugin_declares_the_skills_path(self):
        plugin = self.manifest["plugins"][0]
        self.assertIn("skills", plugin)
        self.assertIsInstance(plugin["skills"], list)
        self.assertGreater(len(plugin["skills"]), 0)

    def test_declared_skills_paths_resolve_to_real_directories(self):
        """The one thing that silently breaks the one-command install if wrong."""
        plugin = self.manifest["plugins"][0]
        for relative in plugin["skills"]:
            with self.subTest(path=relative):
                target = REPO_ROOT / relative
                self.assertTrue(target.is_dir(), f"{relative} does not exist")
                self.assertTrue(
                    (target / "SKILL.md").is_file(),
                    f"{relative} has no SKILL.md -- not a valid skill directory",
                )

    def test_strict_is_false_so_no_separate_plugin_manifest_is_required(self):
        """strict defaults to True, which would require its own
        .claude-plugin/plugin.json inside the source folder. We rely on the
        marketplace entry's own declared `skills` path instead, so this must
        stay False -- flipping it without adding that manifest breaks install."""
        self.assertFalse(self.manifest["plugins"][0]["strict"])

    def test_license_matches_the_repository_license_file(self):
        self.assertEqual(self.manifest["plugins"][0]["license"], "MIT")
        self.assertTrue((REPO_ROOT / "LICENSE").is_file())

    def test_repository_and_homepage_urls_point_at_the_real_repo(self):
        plugin = self.manifest["plugins"][0]
        self.assertIn("github.com/OpenWave-India/veriflow", plugin["repository"])
        self.assertIn("github.com/OpenWave-India/veriflow", plugin["homepage"])

    def test_plugin_description_states_what_and_when(self):
        """Claude Code matches a user's request against this description to
        decide whether to offer the plugin's skill -- same requirement as a
        SKILL.md description."""
        description = self.manifest["plugins"][0]["description"]
        self.assertGreater(len(description), 60)
        self.assertIn("Use when", description)

    def test_manifest_has_no_xml_tags(self):
        """Same constraint Agent Skills frontmatter enforces on descriptions."""
        text = json.dumps(self.manifest)
        self.assertNotIn("<", text.replace('"$schema"', ""))


if __name__ == "__main__":
    unittest.main()

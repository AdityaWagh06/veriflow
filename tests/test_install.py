"""
Tests for the Claude Code skill installer.

The installer writes into a user's home directory or project, so the properties
that matter most are the destructive ones: it must never clobber work it did
not write, it must be reversible, it must be idempotent, and --dry-run must
genuinely change nothing.

Every test installs into a temporary directory. None of them touch the real
~/.claude, and none of them run the installer without an explicit destination.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER = REPO_ROOT / "install.py"
SOURCE_SKILL = REPO_ROOT / "skills" / "veriflow"
INSTALLED_SKILL = REPO_ROOT / ".claude" / "skills" / "veriflow"

_spec = importlib.util.spec_from_file_location("veriflow_installer", INSTALLER)
installer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(installer)


def run_installer(*args: str) -> subprocess.CompletedProcess:
    """Invoke the installer as a user would."""
    return subprocess.run(
        [sys.executable, str(INSTALLER), *args],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(REPO_ROOT),
    )


class TestInstallerSafety(unittest.TestCase):
    """The installer must not surprise anyone."""

    def test_a_destination_scope_is_required(self):
        """There is no default destination, so a bare run cannot write anywhere."""
        proc = run_installer()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("one of the arguments", proc.stderr.lower() + proc.stdout.lower())

    def test_project_and_personal_are_mutually_exclusive(self):
        proc = run_installer("--project", "--personal")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not allowed with", proc.stderr.lower())

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_installer("--project", "--project-root", tmp, "--dry-run")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("nothing was written", proc.stdout.lower())
            self.assertFalse((Path(tmp) / ".claude").exists())

    def test_dry_run_reports_the_exact_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_installer("--project", "--project-root", tmp, "--dry-run")
            expected = str(Path(tmp).resolve() / ".claude" / "skills" / "veriflow")
            self.assertIn(expected, proc.stdout)

    def test_missing_project_root_is_an_error(self):
        proc = run_installer("--project", "--project-root", str(REPO_ROOT / "no-such-dir-9f2a"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("does not exist", proc.stderr)

    def test_refuses_to_overwrite_a_directory_it_did_not_write(self):
        """The central safety property: no silent clobbering of someone's work."""
        with tempfile.TemporaryDirectory() as tmp:
            foreign = Path(tmp) / ".claude" / "skills" / "veriflow"
            foreign.mkdir(parents=True)
            sentinel = foreign / "SKILL.md"
            sentinel.write_text("---\nname: veriflow\n---\nSomeone else's skill.\n", encoding="utf-8")

            proc = run_installer("--project", "--project-root", tmp)

            self.assertEqual(proc.returncode, 1)
            self.assertIn("will not overwrite", proc.stdout)
            self.assertIn("Someone else's skill.", sentinel.read_text(encoding="utf-8"))

    def test_force_backs_up_before_replacing(self):
        """--force is allowed to replace, but never to destroy."""
        with tempfile.TemporaryDirectory() as tmp:
            foreign = Path(tmp) / ".claude" / "skills" / "veriflow"
            foreign.mkdir(parents=True)
            (foreign / "SKILL.md").write_text("original content\n", encoding="utf-8")

            proc = run_installer("--project", "--project-root", tmp, "--force")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("backed up to", proc.stdout)

            backups = list((Path(tmp) / ".claude" / "skills").glob("veriflow.backup-*"))
            self.assertEqual(len(backups), 1, "exactly one backup must be created")
            self.assertIn("original content", (backups[0] / "SKILL.md").read_text(encoding="utf-8"))
            # And the real skill is now installed.
            self.assertTrue((foreign / "scripts" / "run-checks.py").is_file())

    def test_installing_creates_nothing_outside_the_skill_directory(self):
        """Behavioural check: the installer writes one directory and nothing else.

        Asserted by diffing the whole project tree before and after, so a stray
        settings file, lockfile or marker written anywhere else fails the test.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "existing.txt").write_text("untouched\n", encoding="utf-8")
            before = {p.relative_to(root) for p in root.rglob("*")}

            proc = run_installer("--project", "--project-root", tmp)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            after = {p.relative_to(root) for p in root.rglob("*")}
            created = after - before

            allowed_prefix = Path(".claude")
            outside = sorted(
                str(p) for p in created
                if allowed_prefix not in (p, *p.parents)
            )
            self.assertEqual(outside, [], f"installer wrote outside .claude/: {outside}")

            # Pre-existing content is untouched.
            self.assertEqual(
                (root / "existing.txt").read_text(encoding="utf-8"), "untouched\n"
            )

    def test_installer_does_not_modify_claude_code_settings(self):
        """No global configuration: the installer touches no settings file."""
        source = INSTALLER.read_text(encoding="utf-8")
        for forbidden in ("settings.json", "settings.local.json", "winreg", "setx("):
            with self.subTest(token=forbidden):
                self.assertNotIn(
                    forbidden,
                    source,
                    f"the installer must never write {forbidden}",
                )


class TestInstallBehaviour(unittest.TestCase):
    """Installing, updating and verifying."""

    def test_install_copies_the_skill_and_is_discoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_installer("--project", "--project-root", tmp)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            destination = Path(tmp) / ".claude" / "skills" / "veriflow"
            skill_md = destination / "SKILL.md"
            self.assertTrue(skill_md.is_file(), "Claude Code discovers a skill by its SKILL.md")
            self.assertTrue(skill_md.read_text(encoding="utf-8").startswith("---"))
            for required in (
                "scripts/run-checks.py",
                "scripts/detect-project.py",
                "scripts/run-security-tests.py",
                "scripts/security_scanner.py",
                "references/production-test-catalog.json",
                "references/repair-workflow.md",
            ):
                with self.subTest(path=required):
                    self.assertTrue((destination / required).is_file())

    def test_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = run_installer("--project", "--project-root", tmp)
            second = run_installer("--project", "--project-root", tmp)
            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 0)
            self.assertIn("Already up to date", second.stdout)

    def test_install_excludes_bytecode_caches(self):
        """Stale .pyc files can shadow the real module, so they are never copied."""
        with tempfile.TemporaryDirectory() as tmp:
            run_installer("--project", "--project-root", tmp)
            destination = Path(tmp) / ".claude" / "skills" / "veriflow"
            self.assertEqual(list(destination.rglob("__pycache__")), [])
            self.assertEqual(list(destination.rglob("*.pyc")), [])

    def test_install_writes_a_marker_recording_what_it_did(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_installer("--project", "--project-root", tmp)
            marker = Path(tmp) / ".claude" / "skills" / "veriflow" / installer.MARKER_FILENAME
            self.assertTrue(marker.is_file())
            data = json.loads(marker.read_text(encoding="utf-8"))
            self.assertEqual(data["skill"], "veriflow")
            self.assertEqual(data["scope"], "project")
            self.assertGreater(data["file_count"], 10)
            self.assertIn("installed_at", data)

    def test_update_removes_a_file_no_longer_in_the_source(self):
        """A stale file from an older version must not linger."""
        with tempfile.TemporaryDirectory() as tmp:
            run_installer("--project", "--project-root", tmp)
            destination = Path(tmp) / ".claude" / "skills" / "veriflow"
            stale = destination / "references" / "removed-in-this-version.md"
            stale.write_text("left over from an older install\n", encoding="utf-8")

            proc = run_installer("--project", "--project-root", tmp)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertFalse(stale.exists(), "a stale file must be removed on update")

    def test_update_replaces_a_modified_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_installer("--project", "--project-root", tmp)
            destination = Path(tmp) / ".claude" / "skills" / "veriflow"
            target = destination / "SKILL.md"
            target.write_text("tampered\n", encoding="utf-8")

            proc = run_installer("--project", "--project-root", tmp)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                (SOURCE_SKILL / "SKILL.md").read_text(encoding="utf-8"),
            )

    def test_installed_scripts_run_from_their_installed_location(self):
        """The copy must work standalone, not only inside the source tree."""
        with tempfile.TemporaryDirectory() as tmp:
            run_installer("--project", "--project-root", tmp)
            destination = Path(tmp) / ".claude" / "skills" / "veriflow"

            detect = subprocess.run(
                [sys.executable, str(destination / "scripts" / "detect-project.py"), tmp],
                capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(detect.returncode, 0, detect.stderr)
            self.assertIn("detected_types", detect.stdout)

            scan = subprocess.run(
                [sys.executable, str(destination / "scripts" / "run-security-tests.py"), tmp, "--json"],
                capture_output=True, text=True, timeout=180,
            )
            payload = json.loads(scan.stdout)
            self.assertEqual(payload["engine"], "veriflow-security")


class TestVerifyAndUninstall(unittest.TestCase):
    """Diagnosing and reversing an installation."""

    def test_verify_reports_a_missing_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_installer("--project", "--project-root", tmp, "--verify")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("NOT INSTALLED", proc.stdout)

    def test_verify_passes_on_a_fresh_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_installer("--project", "--project-root", tmp)
            proc = run_installer("--project", "--project-root", tmp, "--verify")
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("OK", proc.stdout)

    def test_verify_detects_a_missing_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_installer("--project", "--project-root", tmp)
            (Path(tmp) / ".claude" / "skills" / "veriflow" / "scripts" / "run-checks.py").unlink()
            proc = run_installer("--project", "--project-root", tmp, "--verify")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("run-checks.py", proc.stdout)

    def test_verify_detects_a_stale_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_installer("--project", "--project-root", tmp)
            target = Path(tmp) / ".claude" / "skills" / "veriflow" / "SKILL.md"
            target.write_text("an older version\n", encoding="utf-8")
            proc = run_installer("--project", "--project-root", tmp, "--verify")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("out of date", proc.stdout)

    def test_uninstall_removes_what_it_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_installer("--project", "--project-root", tmp)
            destination = Path(tmp) / ".claude" / "skills" / "veriflow"
            self.assertTrue(destination.is_dir())

            proc = run_installer("--project", "--project-root", tmp, "--uninstall")
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertFalse(destination.exists())

    def test_uninstall_refuses_a_directory_it_did_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            foreign = Path(tmp) / ".claude" / "skills" / "veriflow"
            foreign.mkdir(parents=True)
            (foreign / "SKILL.md").write_text("not ours\n", encoding="utf-8")

            proc = run_installer("--project", "--project-root", tmp, "--uninstall")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("Refusing to remove", proc.stdout)
            self.assertTrue((foreign / "SKILL.md").is_file())

    def test_uninstall_dry_run_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_installer("--project", "--project-root", tmp)
            destination = Path(tmp) / ".claude" / "skills" / "veriflow"
            proc = run_installer("--project", "--project-root", tmp, "--uninstall", "--dry-run")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("Nothing was deleted", proc.stdout)
            self.assertTrue(destination.is_dir())

    def test_uninstall_of_nothing_succeeds_quietly(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_installer("--project", "--project-root", tmp, "--uninstall")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("Nothing installed there", proc.stdout)


class TestCommittedInstallationIsInSync(unittest.TestCase):
    """The repository ships a pre-installed copy at .claude/skills/veriflow.

    It exists so that cloning Veriflow makes the skill immediately discoverable
    with no setup step. The risk is drift: an edit to skills/veriflow that is
    never re-installed leaves two different skills in one repository. This test
    makes that drift a test failure with a one-command fix.
    """

    def test_committed_installation_exists(self):
        self.assertTrue(
            (INSTALLED_SKILL / "SKILL.md").is_file(),
            "run: python install.py --project",
        )

    def test_committed_installation_matches_the_source(self):
        plan = installer.classify(INSTALLED_SKILL, installer.iter_source_files())
        self.assertEqual(
            (plan["new"], plan["changed"], plan["stale"]),
            ([], [], []),
            "the committed .claude/skills/veriflow has drifted from skills/veriflow. "
            "Re-sync with: python install.py --project",
        )

    def test_resolve_personal_destination_points_at_the_documented_path(self):
        """The documented personal path must be the one the code actually uses."""
        expected = Path.home() / ".claude" / "skills" / "veriflow"
        self.assertEqual(installer.personal_skills_dir() / "veriflow", expected)


if __name__ == "__main__":
    unittest.main()

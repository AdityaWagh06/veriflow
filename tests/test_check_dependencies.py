"""
Tests for the dependency identity check (hallucinated/typosquatted package
detection).

Unit tests use an injected fake checker so no real network request is made --
deterministic and fast, matching how the rest of the suite avoids live
network dependencies. One smoke-test class hits the real registries and
reports BLOCKED (skips) rather than failing if the network is unavailable,
same principle Veriflow applies everywhere: an unreachable prerequisite is
never a red result.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from skills.veriflow.scripts.check_dependencies import (
    ALLOWED_REGISTRY_HOSTS,
    PackageFinding,
    UnsafeRegistryHostError,
    _safe_registry_get,
    check_npm_package,
    check_pypi_package,
    discover_manifests,
    parse_package_json,
    parse_requirements_txt,
    preview_dependency_check,
    run_dependency_check,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "skills" / "veriflow" / "scripts" / "check_dependencies.py"


def fake_pypi_found(name, spec, timeout):
    return PackageFinding(
        ecosystem="python", name=name, declared_version=spec, status="FOUND",
        first_release_date="2015-01-01T00:00:00", days_since_first_release=4000,
    )


def fake_pypi_not_found(name, spec, timeout):
    return PackageFinding(ecosystem="python", name=name, declared_version=spec, status="NOT_FOUND")


def fake_pypi_notably_new(name, spec, timeout):
    return PackageFinding(
        ecosystem="python", name=name, declared_version=spec, status="FOUND",
        first_release_date="2026-10-20T00:00:00", days_since_first_release=3, notably_new=True,
    )


def fake_pypi_blocked(name, spec, timeout):
    return PackageFinding(ecosystem="python", name=name, declared_version=spec, status="BLOCKED", error="Connection failed: timed out")


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, timeout=30)


class TestManifestParsing(unittest.TestCase):
    def test_parses_simple_requirements(self):
        text = "flask==2.3.0\nrequests>=2.28\nnumpy\n"
        self.assertEqual(
            parse_requirements_txt(text),
            [("flask", "==2.3.0"), ("requests", ">=2.28"), ("numpy", None)],
        )

    def test_skips_comments_and_includes(self):
        text = "# a comment\n-r other.txt\n-e .\nflask==1.0\n"
        self.assertEqual(parse_requirements_txt(text), [("flask", "==1.0")])

    def test_skips_unparseable_lines_rather_than_guessing(self):
        """A line with garbage after the name must be dropped, not mangled into a fake spec."""
        text = "bad!!!garbage###\nflask==1.0\n"
        result = parse_requirements_txt(text)
        self.assertEqual(result, [("flask", "==1.0")])

    def test_handles_compound_version_specifiers(self):
        text = "django>=3.0,<4.0\n"
        self.assertEqual(parse_requirements_txt(text), [("django", ">=3.0,<4.0")])

    def test_strips_inline_comments(self):
        text = "flask==2.3.0  # pinned for compatibility\n"
        self.assertEqual(parse_requirements_txt(text), [("flask", "==2.3.0")])

    def test_parses_package_json_dependencies_and_dev_dependencies(self):
        text = json.dumps({"dependencies": {"express": "^4.18.0"}, "devDependencies": {"jest": "^29.0.0"}})
        result = parse_package_json(text)
        self.assertIn(("express", "^4.18.0"), result)
        self.assertIn(("jest", "^29.0.0"), result)

    def test_malformed_package_json_returns_empty_not_a_crash(self):
        self.assertEqual(parse_package_json("{ not valid json"), [])

    def test_discover_manifests_finds_requirements_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requirements.txt").write_text("flask\n", encoding="utf-8")
            (root / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
            found = discover_manifests(root)
            names = {p.name for _eco, p in found}
            self.assertEqual(names, {"requirements.txt", "requirements-dev.txt"})

    def test_discover_manifests_does_not_scan_subdirectories(self):
        """A vendored or nested manifest is not this project's own dependency set."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "vendor"
            nested.mkdir()
            (nested / "requirements.txt").write_text("flask\n", encoding="utf-8")
            self.assertEqual(discover_manifests(root), [])


class TestFaultDetection(unittest.TestCase):
    """The core claim: a hallucinated/fake package name is flagged; a real one is not."""

    def test_nonexistent_package_is_flagged_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requirements.txt").write_text("totally-fake-hallucinated-pkg\n", encoding="utf-8")
            result = run_dependency_check(root, checkers={"python": fake_pypi_not_found}, rate_limit_seconds=0)
            self.assertEqual(result["summary"]["NOT_FOUND"], 1)
            self.assertEqual(result["findings"][0]["status"], "NOT_FOUND")

    def test_real_package_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requirements.txt").write_text("flask==2.3.0\n", encoding="utf-8")
            result = run_dependency_check(root, checkers={"python": fake_pypi_found}, rate_limit_seconds=0)
            self.assertEqual(result["summary"], {"FOUND": 1})

    def test_notably_new_package_is_flagged_in_the_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requirements.txt").write_text("brand-new-pkg==1.0.0\n", encoding="utf-8")
            result = run_dependency_check(root, checkers={"python": fake_pypi_notably_new}, rate_limit_seconds=0)
            finding = result["findings"][0]
            self.assertEqual(finding["status"], "FOUND")
            self.assertTrue(finding["notably_new"])

    def test_network_failure_is_blocked_never_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requirements.txt").write_text("flask\n", encoding="utf-8")
            result = run_dependency_check(root, checkers={"python": fake_pypi_blocked}, rate_limit_seconds=0)
            self.assertEqual(result["summary"], {"BLOCKED": 1})
            self.assertNotIn("FOUND", result["summary"])

    def test_mixed_manifest_reports_each_package_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requirements.txt").write_text("flask==2.3.0\nfake-pkg-xyz\n", encoding="utf-8")

            def router(name, spec, timeout):
                return fake_pypi_not_found(name, spec, timeout) if "fake" in name else fake_pypi_found(name, spec, timeout)

            result = run_dependency_check(root, checkers={"python": router}, rate_limit_seconds=0)
            self.assertEqual(result["summary"], {"FOUND": 1, "NOT_FOUND": 1})


class TestPreviewMode(unittest.TestCase):
    """Preview must send no request."""

    def test_preview_lists_planned_packages_without_a_checker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requirements.txt").write_text("flask==2.3.0\n", encoding="utf-8")
            preview = preview_dependency_check(root)
            self.assertEqual(len(preview["packages_planned"]), 1)
            self.assertEqual(preview["packages_planned"][0]["name"], "flask")

    def test_preview_on_empty_project_finds_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            preview = preview_dependency_check(tmp)
            self.assertEqual(preview["manifests_found"], [])
            self.assertEqual(preview["packages_planned"], [])


class TestHostAllowlist(unittest.TestCase):
    """Only the two named registries may ever be contacted."""

    def test_allowlist_contains_exactly_the_two_registries(self):
        self.assertEqual(ALLOWED_REGISTRY_HOSTS, {"pypi.org", "registry.npmjs.org"})

    def test_an_unlisted_host_is_refused(self):
        with self.assertRaises(UnsafeRegistryHostError):
            _safe_registry_get("https://evil.example.com/steal", timeout=1.0)

    def test_pypi_json_url_targets_the_allowed_host(self):
        # Exercises the real URL construction without making the request:
        # an unsafe host would raise before any network call is attempted.
        try:
            _safe_registry_get("https://pypi.org/pypi/flask/json", timeout=0.001)
        except UnsafeRegistryHostError:
            self.fail("pypi.org must be on the allowlist")
        except Exception:
            pass  # a timeout or connection error is fine; only the host check is under test


class TestCliContract(unittest.TestCase):
    def test_preview_is_the_default_and_sends_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "requirements.txt").write_text("flask\n", encoding="utf-8")
            proc = run_cli(tmp)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("preview", proc.stdout.lower())
            self.assertIn("No request was sent", proc.stdout)

    def test_json_preview_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "requirements.txt").write_text("flask\n", encoding="utf-8")
            proc = run_cli(tmp, "--json")
            data = json.loads(proc.stdout)
            self.assertEqual(data["mode"], "preview")

    def test_empty_project_preview_reports_nothing_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli(tmp)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("none", proc.stdout.lower())


class TestLiveRegistrySmokeTest(unittest.TestCase):
    """Hits the real registries once each. Skips gracefully if offline."""

    def test_a_real_well_known_package_resolves_on_pypi(self):
        result = check_pypi_package("requests", None, timeout=10.0)
        if result.status == "BLOCKED":
            self.skipTest(f"PyPI unreachable: {result.error}")
        self.assertEqual(result.status, "FOUND")
        self.assertIsNotNone(result.first_release_date)

    def test_a_fabricated_package_name_is_not_found_on_pypi(self):
        result = check_pypi_package("veriflow-this-package-should-never-exist-zz99", None, timeout=10.0)
        if result.status == "BLOCKED":
            self.skipTest(f"PyPI unreachable: {result.error}")
        self.assertEqual(result.status, "NOT_FOUND")

    def test_a_real_well_known_package_resolves_on_npm(self):
        result = check_npm_package("express", None, timeout=10.0)
        if result.status == "BLOCKED":
            self.skipTest(f"npm registry unreachable: {result.error}")
        self.assertEqual(result.status, "FOUND")

    def test_a_fabricated_package_name_is_not_found_on_npm(self):
        result = check_npm_package("veriflow-this-package-should-never-exist-zz99", None, timeout=10.0)
        if result.status == "BLOCKED":
            self.skipTest(f"npm registry unreachable: {result.error}")
        self.assertEqual(result.status, "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()

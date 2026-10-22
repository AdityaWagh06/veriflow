#!/usr/bin/env python3
"""
Veriflow Dependency Identity Check — catches hallucinated and typosquatted
packages before they are installed.

45.1% of 13,648 developers surveyed reported a hallucinated package or config
costing their team real time (Stack Overflow 2026 Developer Survey, AI
disruption). An AI agent suggests a plausible-looking package name; it either
does not exist (and an attacker can register it the moment it is published),
or it exists but is not what the agent thinks it is.

This script reads a project's dependency manifests and checks each declared
package's identity against its real public registry -- PyPI for Python,
npm for JavaScript/TypeScript -- without installing anything. It never
executes project code and never runs a package manager.

This is the one Veriflow check that deliberately talks to the public internet
rather than a loopback target: identity can only be verified against the real
registry. That is why it is opt-in behind --execute like everything else, and
restricted to exactly two well-known registry hosts rather than being a
general-purpose HTTP client.

Safety boundaries:
  - Preview by default. Without --execute, this only parses manifests and
    lists what *would* be checked; it sends no request.
  - Only two hosts are ever contacted: pypi.org and registry.npmjs.org.
  - Read-only: GET requests only, nothing is installed, nothing is modified.
  - Bounded: per-request timeout and capped response size, matching the
    other engines' safety conventions.
  - A network failure is reported BLOCKED/UNKNOWN, never as a pass and never
    as a crash.

Windows PowerShell examples:

    python check_dependencies.py .
    python check_dependencies.py . --execute
    python check_dependencies.py . --execute --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

#: The only hosts this script will ever contact. Anything else is refused,
#: the same "no general-purpose HTTP client" boundary api_safety enforces for
#: loopback targets, just drawn around a fixed allowlist instead.
ALLOWED_REGISTRY_HOSTS = {"pypi.org", "registry.npmjs.org"}

DEFAULT_TIMEOUT_SECONDS = 8.0

#: Deliberately far larger than the 16-64 KB bound the other engines use for
#: untrusted application output. A registry's full package metadata (every
#: historical release) routinely exceeds a megabyte for a popular package --
#: this is trusted, first-party registry data, not an attacker-controlled
#: response, and truncating it would silently break JSON parsing rather than
#: protect anything.
MAX_RESPONSE_BYTES = 8_388_608  # 8 MB

#: A package whose first release is more recent than this is flagged as
#: notably new -- not proof of anything, just a signal worth a second look,
#: per OWASP's Secure Coding with AI Cheat Sheet guidance on hallucinated
#: dependencies.
NOTABLY_NEW_DAYS = 30


class UnsafeRegistryHostError(ValueError):
    """Raised if a lookup would contact a host outside the fixed allowlist."""


@dataclass
class PackageFinding:
    """Result of checking one declared dependency's identity."""

    ecosystem: str
    name: str
    declared_version: Optional[str]
    status: str  # FOUND | NOT_FOUND | BLOCKED | UNKNOWN
    first_release_date: Optional[str] = None
    days_since_first_release: Optional[int] = None
    notably_new: bool = False
    error: Optional[str] = None
    manifest: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ecosystem": self.ecosystem,
            "name": self.name,
            "declared_version": self.declared_version,
            "status": self.status,
            "first_release_date": self.first_release_date,
            "days_since_first_release": self.days_since_first_release,
            "notably_new": self.notably_new,
            "error": self.error,
            "manifest": self.manifest,
        }


# --------------------------------------------------------------------------- #
# Manifest parsing
# --------------------------------------------------------------------------- #

_REQUIREMENT_LINE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*"
    r"(?P<spec>(?:==|>=|<=|!=|~=|>|<)\s*[A-Za-z0-9.*+!_-]+(?:\s*,\s*(?:==|>=|<=|!=|~=|>|<)\s*[A-Za-z0-9.*+!_-]+)*)?"
    r"\s*(?:;.*)?$"
)


def parse_requirements_txt(text: str) -> List[Tuple[str, Optional[str]]]:
    """Return ``(name, version_spec)`` pairs from a requirements.txt-style file.

    Deliberately simple: skips comments, blank lines, ``-r``/``-e`` includes,
    and anything that is not a plain ``name[spec]`` line. A line this parser
    cannot confidently read is skipped rather than guessed at.
    """
    packages: List[Tuple[str, Optional[str]]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "-e ", "--", "-c ")):
            continue
        # Strip a trailing inline comment.
        line = line.split(" #", 1)[0].strip()
        match = _REQUIREMENT_LINE.match(line)
        if not match:
            continue
        packages.append((match.group("name"), match.group("spec")))
    return packages


def parse_package_json(text: str) -> List[Tuple[str, Optional[str]]]:
    """Return ``(name, version_spec)`` pairs from dependencies + devDependencies."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    packages: List[Tuple[str, Optional[str]]] = []
    for section in ("dependencies", "devDependencies"):
        deps = data.get(section)
        if isinstance(deps, dict):
            for name, spec in deps.items():
                if isinstance(name, str) and name:
                    packages.append((name, spec if isinstance(spec, str) else None))
    return packages


def discover_manifests(root: Path) -> List[Tuple[str, Path]]:
    """Return ``(ecosystem, path)`` pairs for every manifest found at the root.

    Only the project root is scanned, not the whole tree: a requirements.txt
    nested inside a vendored or example directory is not this project's own
    dependency set.
    """
    found: List[Tuple[str, Path]] = []
    for candidate in sorted(root.glob("requirements*.txt")):
        if candidate.is_file():
            found.append(("python", candidate))
    package_json = root / "package.json"
    if package_json.is_file():
        found.append(("javascript", package_json))
    return found


# --------------------------------------------------------------------------- #
# Registry lookups
# --------------------------------------------------------------------------- #


def _safe_registry_get(url: str, timeout: float) -> Tuple[Optional[int], Optional[bytes], Optional[str]]:
    """Issue a bounded GET to an allowlisted registry host.

    Returns ``(status_code, body_bytes, error_message)``. Never raises for a
    network failure -- that is reported through ``error_message`` so a lookup
    failure becomes BLOCKED, not a crash.
    """
    from urllib.parse import urlparse

    host = urlparse(url).hostname or ""
    if host not in ALLOWED_REGISTRY_HOSTS:
        raise UnsafeRegistryHostError(
            f"Refusing to contact '{host}': only {', '.join(sorted(ALLOWED_REGISTRY_HOSTS))} are permitted."
        )

    req = urllib.request.Request(url, headers={"User-Agent": "veriflow-dependency-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Read one byte past the cap: if a full response would exceed it,
            # say so explicitly rather than silently feeding truncated bytes
            # to the JSON parser, which fails with a confusing error instead
            # of the real one.
            body = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return resp.status, None, f"Response exceeds the {MAX_RESPONSE_BYTES} byte cap"
            return resp.status, body, None
    except urllib.error.HTTPError as exc:
        return exc.code, None, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return None, None, f"Connection failed: {exc.reason}"
    except (TimeoutError, OSError) as exc:
        return None, None, f"Request failed: {exc}"


def check_pypi_package(name: str, declared_version: Optional[str], timeout: float = DEFAULT_TIMEOUT_SECONDS) -> PackageFinding:
    """Verify a Python package's identity against PyPI."""
    from urllib.parse import quote

    url = f"https://pypi.org/pypi/{quote(name, safe='')}/json"
    status_code, body, error = _safe_registry_get(url, timeout)

    if error and status_code is None:
        return PackageFinding(ecosystem="python", name=name, declared_version=declared_version, status="BLOCKED", error=error)
    if status_code == 404:
        return PackageFinding(ecosystem="python", name=name, declared_version=declared_version, status="NOT_FOUND")
    if status_code != 200 or not body:
        return PackageFinding(
            ecosystem="python", name=name, declared_version=declared_version, status="UNKNOWN",
            error=error or f"Unexpected HTTP {status_code}",
        )

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return PackageFinding(ecosystem="python", name=name, declared_version=declared_version, status="UNKNOWN", error="Malformed registry response")

    first_release_date, days_since = _earliest_release_date(data.get("releases", {}))
    return PackageFinding(
        ecosystem="python",
        name=name,
        declared_version=declared_version,
        status="FOUND",
        first_release_date=first_release_date,
        days_since_first_release=days_since,
        notably_new=days_since is not None and days_since < NOTABLY_NEW_DAYS,
    )


def check_npm_package(name: str, declared_version: Optional[str], timeout: float = DEFAULT_TIMEOUT_SECONDS) -> PackageFinding:
    """Verify a JavaScript/TypeScript package's identity against the npm registry."""
    from urllib.parse import quote

    # Scoped packages (@scope/name) keep the slash encoded per npm's own convention.
    encoded = quote(name, safe="@/")
    url = f"https://registry.npmjs.org/{encoded}"
    status_code, body, error = _safe_registry_get(url, timeout)

    if error and status_code is None:
        return PackageFinding(ecosystem="javascript", name=name, declared_version=declared_version, status="BLOCKED", error=error)
    if status_code == 404:
        return PackageFinding(ecosystem="javascript", name=name, declared_version=declared_version, status="NOT_FOUND")
    if status_code != 200 or not body:
        return PackageFinding(
            ecosystem="javascript", name=name, declared_version=declared_version, status="UNKNOWN",
            error=error or f"Unexpected HTTP {status_code}",
        )

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return PackageFinding(ecosystem="javascript", name=name, declared_version=declared_version, status="UNKNOWN", error="Malformed registry response")

    created = (data.get("time") or {}).get("created")
    days_since = _days_since_iso(created) if created else None
    return PackageFinding(
        ecosystem="javascript",
        name=name,
        declared_version=declared_version,
        status="FOUND",
        first_release_date=created,
        days_since_first_release=days_since,
        notably_new=days_since is not None and days_since < NOTABLY_NEW_DAYS,
    )


def _days_since_iso(iso_timestamp: str) -> Optional[int]:
    import datetime

    try:
        parsed = datetime.datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    return max(0, (now - parsed).days)


def _earliest_release_date(releases: Dict[str, Any]) -> Tuple[Optional[str], Optional[int]]:
    """Return the earliest upload timestamp across a PyPI package's releases."""
    earliest: Optional[str] = None
    for files in releases.values():
        if not isinstance(files, list):
            continue
        for file_info in files:
            timestamp = file_info.get("upload_time_iso_8601") or file_info.get("upload_time")
            if timestamp and (earliest is None or timestamp < earliest):
                earliest = timestamp
    if earliest is None:
        return None, None
    return earliest, _days_since_iso(earliest)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

#: Lookup function per ecosystem, injectable so tests never need the real network.
_CHECKERS: Dict[str, Callable[[str, Optional[str], float], PackageFinding]] = {
    "python": check_pypi_package,
    "javascript": check_npm_package,
}


def preview_dependency_check(root: Path | str) -> Dict[str, Any]:
    """Describe what would be checked. Sends no request."""
    root_path = Path(root).resolve()
    manifests = discover_manifests(root_path)
    planned: List[Dict[str, Any]] = []
    for ecosystem, manifest_path in manifests:
        text = manifest_path.read_text(encoding="utf-8", errors="replace")
        parser = parse_requirements_txt if ecosystem == "python" else parse_package_json
        for name, spec in parser(text):
            planned.append({"ecosystem": ecosystem, "name": name, "declared_version": spec, "manifest": str(manifest_path.name)})
    return {
        "manifests_found": [str(p.name) for _eco, p in manifests],
        "packages_planned": planned,
    }


def run_dependency_check(
    root: Path | str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    rate_limit_seconds: float = 0.1,
    checkers: Optional[Dict[str, Callable[[str, Optional[str], float], PackageFinding]]] = None,
) -> Dict[str, Any]:
    """Check every declared dependency's identity against its real registry.

    Args:
        checkers: Override the ecosystem->lookup-function mapping. Tests pass
            a fake here so no real network request is made; the default is
            the real PyPI/npm lookups.
        rate_limit_seconds: A small pause between requests, so a manifest with
            many dependencies does not hammer a public registry.

    Returns:
        A JSON-serialisable dict with one finding per declared package and a
        severity-free summary count by status.
    """
    root_path = Path(root).resolve()
    manifests = discover_manifests(root_path)
    lookup = checkers or _CHECKERS

    findings: List[PackageFinding] = []
    for ecosystem, manifest_path in manifests:
        text = manifest_path.read_text(encoding="utf-8", errors="replace")
        parser = parse_requirements_txt if ecosystem == "python" else parse_package_json
        checker = lookup.get(ecosystem)
        packages = parser(text)
        for index, (name, spec) in enumerate(packages):
            if checker is None:
                findings.append(
                    PackageFinding(
                        ecosystem=ecosystem, name=name, declared_version=spec, status="BLOCKED",
                        error=f"No checker available for ecosystem '{ecosystem}'", manifest=manifest_path.name,
                    )
                )
                continue
            finding = checker(name, spec, timeout)
            finding.manifest = manifest_path.name
            findings.append(finding)
            if index < len(packages) - 1 and rate_limit_seconds:
                time.sleep(rate_limit_seconds)

    counts: Dict[str, int] = {}
    for finding in findings:
        counts[finding.status] = counts.get(finding.status, 0) + 1

    return {
        "engine": "veriflow-dependency-check",
        "root": str(root_path),
        "manifests_checked": [p.name for _eco, p in manifests],
        "total_packages": len(findings),
        "summary": counts,
        "findings": [f.to_dict() for f in findings],
        "limitations": [
            "Confirms the package name exists on its registry and reports how recently it first "
            "appeared there. It cannot confirm the installed code matches what the agent intended, "
            "and a newly registered name is not proof of malicious intent by itself.",
            "No vulnerability (CVE) data is checked here -- run pip-audit, npm audit or an "
            "equivalent tool separately for known-vulnerability coverage.",
            "Only direct dependencies declared in the manifest are checked, not their transitive "
            "dependencies.",
        ],
    }


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #


def format_report(result: Dict[str, Any]) -> str:
    lines = [
        "=" * 64,
        "Veriflow -- Dependency Identity Check",
        "=" * 64,
        f"Root:      {result['root']}",
        f"Manifests: {', '.join(result['manifests_checked']) or '(none found)'}",
        f"Packages:  {result['total_packages']}",
    ]
    if result["summary"]:
        lines.append("Summary:   " + " ".join(f"{k}={v}" for k, v in result["summary"].items()))
    lines.append("-" * 64)

    flagged = [f for f in result["findings"] if f["status"] != "FOUND" or f["notably_new"]]
    if not flagged:
        lines.append("Every declared package resolved on its registry; none are notably new.")
    for finding in flagged:
        tag = finding["status"]
        if finding["status"] == "FOUND" and finding["notably_new"]:
            tag = "NOTABLY_NEW"
        lines.append(f"  [{tag}] {finding['ecosystem']}: {finding['name']} ({finding['manifest']})")
        if finding["status"] == "NOT_FOUND":
            lines.append("      Does not exist on the registry. Verify the name before using it.")
        elif finding["notably_new"]:
            lines.append(
                f"      First published {finding['days_since_first_release']} day(s) ago "
                f"({finding['first_release_date']}). Confirm this is the package you intended."
            )
        if finding.get("error"):
            lines.append(f"      {finding['error']}")

    lines.extend(["-" * 64, "Limitations:"])
    for limitation in result["limitations"]:
        lines.append(f"  - {limitation}")
    lines.append("=" * 64)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_dependencies.py",
        description="Verify declared dependencies' identity against PyPI / npm.",
        epilog=(
            "Contacts only pypi.org and registry.npmjs.org, and only with --execute. "
            "Preview lists what would be checked and sends no request."
        ),
    )
    parser.add_argument("root", nargs="?", default=".", help="Project directory to check (default: current directory).")
    parser.add_argument("--execute", action="store_true", help="Actually query the registries. Without it, preview only.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="Per-request timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Emit a structured JSON report.")
    args = parser.parse_args(argv)

    if not args.execute:
        preview = preview_dependency_check(args.root)
        if args.json:
            print(json.dumps({"mode": "preview", **preview}, indent=2))
        else:
            print("=" * 64)
            print("Veriflow -- Dependency Identity Check (preview)")
            print("=" * 64)
            print(f"Manifests found: {', '.join(preview['manifests_found']) or '(none)'}")
            print(f"Packages that would be checked: {len(preview['packages_planned'])}")
            for pkg in preview["packages_planned"]:
                print(f"  {pkg['ecosystem']}: {pkg['name']} ({pkg['manifest']})")
            print("-" * 64)
            print("No request was sent. Pass --execute to query pypi.org / registry.npmjs.org.")
            print("=" * 64)
        return 0

    result = run_dependency_check(args.root, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_report(result))

    return 1 if result["summary"].get("NOT_FOUND", 0) else 0


if __name__ == "__main__":
    sys.exit(main())

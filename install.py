#!/usr/bin/env python3
"""
Veriflow installer for Claude Code and Codex.

Both agents use the same open Agent Skills shape -- a directory containing a
``SKILL.md`` with ``name``/``description`` frontmatter, read with progressive
disclosure -- but they scan different paths:

  Claude Code:
    - ``<project>/.claude/skills/<name>/SKILL.md``  (project: this repo only)
    - ``~/.claude/skills/<name>/SKILL.md``          (personal: all your projects)

  Codex (CLI, IDE extension, app):
    - ``<project>/.agents/skills/<name>/SKILL.md``  (project: this repo only)
    - ``~/.agents/skills/<name>/SKILL.md``          (personal: all your projects)

Veriflow's source tree lives at ``skills/veriflow/``, which neither agent
scans directly. This script copies that one directory into whichever of the
four locations above you ask for. The content is identical for both agents --
only the destination path differs -- so nothing is duplicated or maintained
twice.

Design rules:

- **Nothing happens without being told where.** ``--project`` or ``--personal``
  is required; there is no default scope. ``--platform`` defaults to ``both``,
  since installing for an agent you don't use costs nothing and installing for
  only one is one flag away (``--platform claude`` or ``--platform codex``).
- **Dry run first.** ``--dry-run`` prints every file operation and changes
  nothing.
- **Idempotent.** Re-running produces the same result and reports what changed.
- **Never clobbers silently.** An existing installation that Veriflow did not
  write is backed up to a timestamped sibling directory, and the backup path is
  printed. ``--force`` is required to replace it at all.
- **Nothing global is touched.** No agent setting, no registry key, no PATH
  entry, no environment variable. Only the skill directory or directories
  requested.
- **Reversible.** ``--uninstall`` removes exactly what was installed, and
  refuses to touch a directory that is not a Veriflow installation.

Windows PowerShell examples:

    python install.py --project --dry-run
    python install.py --project                        # both agents
    python install.py --project --platform claude       # Claude Code only
    python install.py --personal --platform codex        # Codex only
    python install.py --personal --uninstall
    python install.py --project --verify
"""

from __future__ import annotations

import argparse
import datetime
import filecmp
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

#: Name of the installed skill directory. Both agents match on this.
SKILL_NAME = "veriflow"

#: Source directory, relative to this script.
SOURCE_DIR = Path(__file__).resolve().parent / "skills" / SKILL_NAME

#: The skills-folder name each agent scans for, keyed by platform id.
#: Both are the same open Agent Skills shape; only this leaf name differs.
PLATFORM_SKILLS_DIRNAME: Dict[str, str] = {
    "claude": ".claude",
    "codex": ".agents",
}

#: Display name for messages, keyed by platform id.
PLATFORM_LABEL: Dict[str, str] = {
    "claude": "Claude Code",
    "codex": "Codex",
}

#: Marker written into every installation. Its presence is what lets
#: --uninstall tell a Veriflow installation from a directory someone else owns.
MARKER_FILENAME = ".veriflow-install.json"

#: Directories and files never copied: build artefacts and caches add weight
#: and can carry stale bytecode that shadows the real module.
EXCLUDED_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pyd"}


class InstallError(RuntimeError):
    """Raised for a condition the user must resolve before installing."""


# --------------------------------------------------------------------------- #
# Destination resolution
# --------------------------------------------------------------------------- #


def personal_skills_dir(platform: str) -> Path:
    """Return the per-user skills directory for ``platform`` ("claude" or "codex").

    ``Path.home()`` resolves ``%USERPROFILE%`` on Windows and ``$HOME``
    elsewhere, which is exactly where both agents look.
    """
    return Path.home() / PLATFORM_SKILLS_DIRNAME[platform] / "skills"


def project_skills_dir(project_root: Path, platform: str) -> Path:
    """Return the project-level skills directory for ``platform``."""
    return project_root / PLATFORM_SKILLS_DIRNAME[platform] / "skills"


def resolve_destinations(args: argparse.Namespace) -> List[Tuple[Path, str, str]]:
    """Return one ``(destination, scope_label, platform)`` tuple per requested platform.

    ``args.platforms`` is always a non-empty list of ``"claude"`` / ``"codex"``,
    so this always returns at least one destination.
    """
    destinations: List[Tuple[Path, str, str]] = []

    if args.personal:
        for platform in args.platforms:
            destinations.append((personal_skills_dir(platform) / SKILL_NAME, "personal", platform))
        return destinations

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        raise InstallError(f"Project root does not exist: {project_root}")
    for platform in args.platforms:
        destinations.append((project_skills_dir(project_root, platform) / SKILL_NAME, "project", platform))
    return destinations


# --------------------------------------------------------------------------- #
# File planning
# --------------------------------------------------------------------------- #


def iter_source_files() -> List[Path]:
    """Return every file to install, as paths relative to the source directory."""
    if not SOURCE_DIR.is_dir():
        raise InstallError(
            f"Veriflow source directory not found: {SOURCE_DIR}\n"
            "Run this script from a Veriflow checkout."
        )

    collected: List[Path] = []
    for current, dir_names, file_names in os.walk(SOURCE_DIR):
        dir_names[:] = sorted(d for d in dir_names if d not in EXCLUDED_DIR_NAMES)
        for file_name in sorted(file_names):
            if Path(file_name).suffix in EXCLUDED_SUFFIXES:
                continue
            collected.append((Path(current) / file_name).relative_to(SOURCE_DIR))
    return collected


def read_marker(destination: Path) -> Optional[Dict[str, object]]:
    """Return the installation marker, or None when absent or unreadable."""
    marker = destination / MARKER_FILENAME
    try:
        if not marker.is_file():
            return None
        return json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def classify(destination: Path, relative_files: List[Path]) -> Dict[str, List[Path]]:
    """Compare source against destination without changing anything.

    Returns the files to add, the files whose content differs, the files already
    identical, and the files present at the destination that the source no
    longer has (stale, from an older version).
    """
    plan: Dict[str, List[Path]] = {"new": [], "changed": [], "identical": [], "stale": []}

    for relative in relative_files:
        target = destination / relative
        if not target.exists():
            plan["new"].append(relative)
        elif filecmp.cmp(SOURCE_DIR / relative, target, shallow=False):
            plan["identical"].append(relative)
        else:
            plan["changed"].append(relative)

    if destination.is_dir():
        expected = set(relative_files)
        for current, dir_names, file_names in os.walk(destination):
            dir_names[:] = [d for d in dir_names if d not in EXCLUDED_DIR_NAMES]
            for file_name in file_names:
                if file_name == MARKER_FILENAME:
                    continue
                relative = (Path(current) / file_name).relative_to(destination)
                if relative not in expected and Path(file_name).suffix not in EXCLUDED_SUFFIXES:
                    plan["stale"].append(relative)

    return plan


# --------------------------------------------------------------------------- #
# Install / uninstall
# --------------------------------------------------------------------------- #


def back_up(destination: Path, dry_run: bool) -> Path:
    """Move an existing directory aside to a timestamped sibling."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = destination.with_name(f"{destination.name}.backup-{stamp}")
    if not dry_run:
        shutil.move(str(destination), str(backup))
    return backup


def install(destination: Path, scope: str, platform: str, args: argparse.Namespace) -> int:
    """Copy the skill into ``destination``. Returns a process exit code."""
    relative_files = iter_source_files()
    marker = read_marker(destination)
    backup: Optional[Path] = None

    print(f"Source:      {SOURCE_DIR}")
    print(f"Destination: {destination}   [{scope} / {PLATFORM_LABEL[platform]}]")
    print(f"Files:       {len(relative_files)}")
    print()

    if destination.exists():
        if marker is None:
            # A directory Veriflow did not write. Do not touch it without being told to.
            if not args.force:
                print(f"A skill already exists at {destination}, and it was not installed by Veriflow")
                print(f"(no {MARKER_FILENAME} marker found).")
                print()
                print("Veriflow will not overwrite it. Your options:")
                print("  - Inspect it, and rerun with --force to replace it (a backup is kept).")
                print("  - Install to the other scope instead (--personal / --project).")
                print("  - Remove or rename it yourself first.")
                return 1
            backup = back_up(destination, args.dry_run)
            print(f"Existing directory backed up to: {backup}")
            print()
        else:
            installed_version = marker.get("veriflow_source", "unknown")
            print(f"Updating an existing Veriflow installation (previous source: {installed_version}).")
            print()

    plan = classify(destination, relative_files)

    for label, key in (
        ("add", "new"),
        ("update", "changed"),
        ("unchanged", "identical"),
        ("remove (not in this version)", "stale"),
    ):
        items = plan[key]
        if not items:
            continue
        print(f"{label}: {len(items)}")
        if args.verbose or len(items) <= 12:
            for relative in items:
                print(f"    {relative.as_posix()}")
        print()

    if args.dry_run:
        print("Dry run: nothing was written.")
        print(f"Rerun without --dry-run to install into {destination}")
        return 0

    if not (plan["new"] or plan["changed"] or plan["stale"]) and marker is not None:
        print("Already up to date. Nothing to do.")
        return 0

    destination.mkdir(parents=True, exist_ok=True)

    for relative in plan["new"] + plan["changed"]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE_DIR / relative, target)

    for relative in plan["stale"]:
        try:
            (destination / relative).unlink()
        except OSError as exc:
            print(f"Warning: could not remove stale file {relative.as_posix()}: {exc}")

    (destination / MARKER_FILENAME).write_text(
        json.dumps(
            {
                "skill": SKILL_NAME,
                "scope": scope,
                "veriflow_source": str(SOURCE_DIR),
                "installed_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "file_count": len(relative_files),
                "backup": str(backup) if backup else None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Installed {len(relative_files)} files to {destination}")
    print()
    print("Next steps:")
    print(f"  1. Restart {PLATFORM_LABEL[platform]}, or start a new session, so it rescans skills.")
    print("  2. Confirm discovery by asking: \"what skills do you have available?\"")
    print(f"  3. Verify the installation: python install.py --{scope} --platform {platform} --verify")
    if scope == "personal":
        print()
        print("Note: a personal installation applies to every project you open.")
    return 0


def uninstall(destination: Path, scope: str, platform: str, args: argparse.Namespace) -> int:
    """Remove an installation, refusing anything Veriflow did not write."""
    print(f"Target: {destination}   [{scope} / {PLATFORM_LABEL[platform]}]")

    if not destination.exists():
        print("Nothing installed there. Nothing to do.")
        return 0

    if read_marker(destination) is None:
        print()
        print(f"Refusing to remove {destination}: it has no {MARKER_FILENAME} marker,")
        print("so it was not installed by this script and may be your own work.")
        print("Remove it manually if that is what you intend.")
        return 1

    if args.dry_run:
        print("Dry run: this directory would be removed. Nothing was deleted.")
        return 0

    shutil.rmtree(destination)
    print("Removed.")
    print(f"Restart {PLATFORM_LABEL[platform]} so it stops offering the skill.")

    # Clean up the parent only when empty, so a sibling skill is never affected.
    parent = destination.parent
    try:
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            print(f"Removed now-empty {parent}")
    except OSError:
        pass
    return 0


def verify(destination: Path, scope: str, platform: str) -> int:
    """Check that an installation is complete and discoverable."""
    print(f"Verifying: {destination}   [{scope} / {PLATFORM_LABEL[platform]}]")
    print()

    problems: List[str] = []

    if not destination.is_dir():
        print(f"NOT INSTALLED: {destination} does not exist.")
        print(f"Install it with: python install.py --{scope} --platform {platform}")
        return 1

    skill_md = destination / "SKILL.md"
    if not skill_md.is_file():
        problems.append(f"SKILL.md is missing, so {PLATFORM_LABEL[platform]} cannot discover the skill.")
    else:
        text = skill_md.read_text(encoding="utf-8")
        if not text.startswith("---"):
            problems.append("SKILL.md does not begin with YAML frontmatter.")
        else:
            try:
                frontmatter = text[4 : text.index(chr(10) + "---", 4)]
            except ValueError:
                frontmatter = ""
                problems.append("SKILL.md frontmatter is not terminated by a '---' line.")
            if "name:" not in frontmatter:
                problems.append("SKILL.md frontmatter has no 'name' field.")
            if "description:" not in frontmatter:
                problems.append("SKILL.md frontmatter has no 'description' field.")

    required = [
        Path("scripts/run-checks.py"),
        Path("scripts/detect-project.py"),
        Path("scripts/run-security-tests.py"),
        Path("scripts/security_scanner.py"),
        Path("references/production-test-catalog.json"),
        Path("references/repair-workflow.md"),
    ]
    for relative in required:
        if not (destination / relative).is_file():
            problems.append(f"missing: {relative.as_posix()}")

    marker = read_marker(destination)
    if marker is None:
        problems.append(f"no {MARKER_FILENAME}; this directory was not installed by install.py.")

    plan = classify(destination, iter_source_files())
    if plan["changed"] or plan["new"]:
        problems.append(
            f"out of date: {len(plan['new'])} file(s) missing and "
            f"{len(plan['changed'])} file(s) differ from the source. "
            f"Rerun: python install.py --{scope} --platform {platform}"
        )

    if problems:
        print("PROBLEMS FOUND:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("OK")
    print(f"  SKILL.md present with valid frontmatter")
    print(f"  all required scripts and references present")
    print(f"  installed {marker.get('file_count')} files at {marker.get('installed_at')}")
    print()
    print(f"{PLATFORM_LABEL[platform]} discovers skills at session start. If it does not offer")
    print("Veriflow, start a new session and ask: \"what skills do you have available?\"")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Install the Veriflow skill where Claude Code and/or Codex can discover it.",
        epilog=(
            "Claude Code reads .claude/skills/ in a project and ~/.claude/skills/ for your "
            "user; Codex reads .agents/skills/ and ~/.agents/skills/ the same way. This "
            "script writes the skill directory into the place(s) requested and changes no "
            "global setting."
        ),
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument(
        "--project",
        action="store_true",
        help="Install into this project only (<project>/.claude/skills/veriflow and/or .agents/skills/veriflow).",
    )
    scope.add_argument(
        "--personal",
        action="store_true",
        help="Install for all of your projects (~/.claude/skills/veriflow and/or ~/.agents/skills/veriflow).",
    )
    parser.add_argument(
        "--platform",
        choices=("claude", "codex", "both"),
        default="both",
        help="Which agent to install for (default: both -- installing for one you don't use costs nothing).",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project directory for --project (default: current directory).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen; write nothing.")
    parser.add_argument("--uninstall", action="store_true", help="Remove a previous installation.")
    parser.add_argument("--verify", action="store_true", help="Check an installation is complete and current.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace a non-Veriflow skill directory. The existing one is backed up first.",
    )
    parser.add_argument("--verbose", action="store_true", help="List every file, not just a summary.")
    args = parser.parse_args(argv)

    if args.uninstall and args.verify:
        parser.error("--uninstall and --verify cannot be combined.")

    args.platforms = ["claude", "codex"] if args.platform == "both" else [args.platform]

    try:
        destinations = resolve_destinations(args)
        print("Veriflow skill installer")
        print("=" * 60)

        exit_code = 0
        for index, (destination, scope_label, platform) in enumerate(destinations):
            if index > 0:
                print()
                print("-" * 60)
                print()
            if args.verify:
                result = verify(destination, scope_label, platform)
            elif args.uninstall:
                result = uninstall(destination, scope_label, platform, args)
            else:
                result = install(destination, scope_label, platform, args)
            exit_code = max(exit_code, result)
        return exit_code
    except InstallError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except PermissionError as exc:
        print(f"Error: permission denied: {exc}", file=sys.stderr)
        print("Choose a destination you can write to, or adjust its permissions.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

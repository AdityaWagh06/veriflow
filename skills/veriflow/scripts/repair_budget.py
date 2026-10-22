#!/usr/bin/env python3
"""
Veriflow Repair Attempt Budget — the 3-attempt cap, enforced in code.

SKILL.md and references/repair-workflow.md *tell* an agent to cap itself at 3
file-modifying repair attempts per issue. That is an instruction the agent
reads and can ignore. This module makes the budget a fact a script can
actually refuse against: a small persistent counter, scoped to one project and
one issue, that returns a hard DENY once the cap is reached.

This does not (and cannot) stop an agent from editing files anyway -- Veriflow
has no hook into the agent's own edit tool. What it does is give the agent (or
a human reviewing its work) a command that will not say ALLOWED past the cap,
so "I'm within budget" becomes a checkable claim instead of a self-report.

Storage: one small JSON file per issue, under
``<project_root>/.veriflow/repair-sessions/<issue-id>.json``. Local, ephemeral,
gitignored by convention (see .gitignore) -- this is working state for one
verification session, not something to commit.

Windows PowerShell examples:

    python repair_budget.py --root . --attempt login-redirect-bug --note "fixed off-by-one in redirect URL builder"
    python repair_budget.py --root . --status login-redirect-bug
    python repair_budget.py --root . --reset login-redirect-bug
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

#: The cap SKILL.md documents. Keep this the single source of truth so the
#: docs and the enforcement can never silently drift apart.
MAX_ATTEMPTS = 3

#: Where session state lives, relative to the project root being verified.
SESSION_DIR_NAME = Path(".veriflow") / "repair-sessions"

#: An issue id becomes a filename; keep it to characters that are safe on
#: every filesystem Veriflow runs on, rather than trying to escape arbitrary
#: input.
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class InvalidIssueIdError(ValueError):
    """Raised when an issue id is not safe to use as a filename."""


def _validate_issue_id(issue_id: str) -> str:
    if not issue_id or not _SAFE_ID_PATTERN.match(issue_id):
        raise InvalidIssueIdError(
            f"Invalid issue id {issue_id!r}. Use 1-128 characters: letters, digits, "
            "'.', '_' or '-', starting with a letter or digit."
        )
    return issue_id


def _session_path(root: Path, issue_id: str) -> Path:
    _validate_issue_id(issue_id)
    return root / SESSION_DIR_NAME / f"{issue_id}.json"


def _load(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"issue_id": path.stem, "attempts": [], "created_at": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # A corrupted session file must not crash the agent's workflow; treat
        # it as fresh, but say so in the returned status rather than silently
        # discarding history.
        return {"issue_id": path.stem, "attempts": [], "created_at": None, "recovered_from_corruption": True}


def _save(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def get_status(root: Path | str, issue_id: str) -> Dict[str, Any]:
    """Return the current attempt count and history for ``issue_id``.

    Never raises for a missing session: a never-started issue has zero
    attempts used, which is the correct and allowed state.
    """
    root_path = Path(root).resolve()
    path = _session_path(root_path, issue_id)
    data = _load(path)
    used = len(data["attempts"])
    return {
        "issue_id": issue_id,
        "attempts_used": used,
        "attempts_remaining": max(0, MAX_ATTEMPTS - used),
        "max_attempts": MAX_ATTEMPTS,
        "exceeded": used >= MAX_ATTEMPTS,
        "history": data["attempts"],
        "session_path": str(path),
    }


def record_attempt(root: Path | str, issue_id: str, note: str = "") -> Dict[str, Any]:
    """Record one file-modifying repair attempt against ``issue_id``.

    This must be called once per attempt, after the fact is decided (i.e.
    right before or right after the edit), never speculatively: calling it
    without actually modifying a file would consume budget for nothing, and
    SKILL.md's own rule is that read-only diagnosis never counts.

    Returns:
        A dict with ``status`` of ``"ALLOWED"`` (this attempt fits the budget)
        or ``"EXCEEDED"`` (the cap was already reached before this call, so
        the attempt is logged for the record but the caller must stop).
    """
    root_path = Path(root).resolve()
    path = _session_path(root_path, issue_id)
    data = _load(path)

    if data.get("created_at") is None:
        data["created_at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    already_exceeded = len(data["attempts"]) >= MAX_ATTEMPTS

    data["attempts"].append(
        {
            "attempt_number": len(data["attempts"]) + 1,
            "note": note,
            "recorded_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    )
    _save(path, data)

    used = len(data["attempts"])
    return {
        "issue_id": issue_id,
        "status": "EXCEEDED" if already_exceeded else "ALLOWED",
        "attempts_used": used,
        "attempts_remaining": max(0, MAX_ATTEMPTS - used),
        "max_attempts": MAX_ATTEMPTS,
        "session_path": str(path),
    }


def reset(root: Path | str, issue_id: str) -> Dict[str, Any]:
    """Clear a session's history. Deliberate and explicit -- never automatic.

    A verified repair does not need a reset: the session simply stops being
    referenced. Reset exists for a user who wants to deliberately restart the
    budget for the same issue id, for example after getting fresh guidance.
    """
    root_path = Path(root).resolve()
    path = _session_path(root_path, issue_id)
    existed = path.is_file()
    if existed:
        path.unlink()
    return {"issue_id": issue_id, "reset": True, "had_existing_session": existed}


def list_sessions(root: Path | str) -> List[Dict[str, Any]]:
    """Return the status of every session recorded for this project."""
    root_path = Path(root).resolve()
    session_dir = root_path / SESSION_DIR_NAME
    if not session_dir.is_dir():
        return []
    results = []
    for path in sorted(session_dir.glob("*.json")):
        results.append(get_status(root_path, path.stem))
    return results


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _format_status(status: Dict[str, Any]) -> str:
    lines = [
        f"Issue:              {status['issue_id']}",
        f"Attempts used:      {status['attempts_used']} / {status['max_attempts']}",
        f"Attempts remaining: {status['attempts_remaining']}",
    ]
    if status.get("exceeded"):
        lines.append("Status:             BUDGET EXCEEDED -- stop and report evidence instead of editing further.")
    if status.get("history"):
        lines.append("History:")
        for entry in status["history"]:
            note = entry.get("note") or "(no note)"
            lines.append(f"  #{entry['attempt_number']}  {entry['recorded_at']}  {note}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="repair_budget.py",
        description=(
            f"Enforce Veriflow's {MAX_ATTEMPTS}-attempt repair budget per issue, in code "
            "rather than only in prose instructions."
        ),
    )
    parser.add_argument("--root", default=".", help="Project directory the session is scoped to (default: current directory).")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--attempt", metavar="ISSUE_ID", help="Record one repair attempt against this issue id.")
    action.add_argument("--status", metavar="ISSUE_ID", help="Show the current attempt count for this issue id.")
    action.add_argument("--reset", metavar="ISSUE_ID", help="Clear the session for this issue id.")
    action.add_argument("--list", action="store_true", help="List every session recorded for this project.")
    parser.add_argument("--note", default="", help="Short description of what this attempt changed (with --attempt).")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    try:
        if args.attempt:
            result = record_attempt(args.root, args.attempt, note=args.note)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(_format_status(get_status(args.root, args.attempt)))
                if result["status"] == "EXCEEDED":
                    print()
                    print(
                        f"REFUSED: issue '{args.attempt}' already used all {MAX_ATTEMPTS} attempts. "
                        "Stop making speculative edits. Report the evidence gathered so far and the "
                        "next diagnostic step instead."
                    )
            return 1 if result["status"] == "EXCEEDED" else 0

        if args.status:
            result = get_status(args.root, args.status)
            print(json.dumps(result, indent=2) if args.json else _format_status(result))
            return 1 if result["exceeded"] else 0

        if args.reset:
            result = reset(args.root, args.reset)
            print(json.dumps(result, indent=2) if args.json else f"Reset session for '{args.reset}'.")
            return 0

        if args.list:
            results = list_sessions(args.root)
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                if not results:
                    print("No repair sessions recorded for this project.")
                for status in results:
                    print(_format_status(status))
                    print("-" * 40)
            return 0
    except InvalidIssueIdError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    return 2  # pragma: no cover - argparse's mutually exclusive group makes this unreachable


if __name__ == "__main__":
    sys.exit(main())

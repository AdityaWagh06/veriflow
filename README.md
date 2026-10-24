# Veriflow

Veriflow is a verification toolkit — and an installable agent skill for both
**Claude Code** and **Codex** — that helps AI coding agents (and the humans
reviewing them) verify code changes honestly instead of just claiming success.

It discovers a project's real checks, runs them safely, scans for security
defects, diagnoses failures from actual evidence, applies bounded minimal
repairs, and reports exactly what passed, what failed, what was blocked, and
what remains unknown. No step can be silently skipped and reported as a pass.

## Why this exists

An AI coding agent can say "all tests pass" without running anything. It can
quietly weaken an assertion to make a test green. It can treat a missing tool
as a pass. Veriflow's result states are built so none of that can happen
silently — and it ships as a skill both major coding agents can discover and
load automatically, not a script you have to remember to run.

### What Claude Code and Codex don't do on their own

Both are general-purpose coding agents with shell and file access — they can
technically run anything you tell them to. What neither ships with is:

- **A real security scanner.** Ask either to "check for vulnerabilities" and
  you get the model's judgment, with no deterministic rule set behind it.
  Veriflow's 26 static rules + 9 live checks are actual pattern-matching and
  HTTP-probing code, each proven against a fault that it must catch.
- **A dependency identity check.** Neither verifies that a package an agent
  just suggested actually exists on its registry before you install it.
  `check_dependencies.py` does, against the real PyPI/npm.
- **A structural result vocabulary.** By default an agent just writes prose
  about what happened — nothing stops it from saying "tests pass" when a
  tool was missing. Veriflow's 7 result states make that distinction a type,
  not a self-report.
- **An enforced repair budget.** "I'll only try 3 fixes" is a sentence an
  agent can simply not honor. `repair_budget.py` persists a real counter and
  refuses the 4th attempt in code.
- **Credential redaction on command output.** When either agent shows you
  raw command output, a leaked secret in it is a leaked secret in your
  terminal. Veriflow redacts before anything is reported.

What's **not** unique: the preview/execute split, the process-safety
conventions (argument lists, timeouts, bounded output) — an agent could
write equivalent code if asked. The value here is that it's already written,
already tested against real faults, and ships as a skill instead of
something you'd have to describe from scratch every session.

## What it does

- **Discovers real checks** — detects the project's ecosystem (Python,
  JavaScript/TypeScript, Rust, Go, Java, .NET) and the test/lint/type-check/
  build commands it actually has, without running them.
- **Full project audit, one command** — `run-audit.py` combines project
  detection, the static security scan, core check execution, and a
  production-readiness catalog scope snapshot into a single verdict and an
  optional shareable Markdown report. See [a real example](#see-it-work) below.
- **Static + live security scanning** — 26 static rules (secrets, injection,
  unsafe deserialization, weak crypto, AI-agent supply-chain patterns) that
  need no setup at all, plus 9 opt-in live checks (security headers, cookie
  flags, auth gates, IDOR, CSRF, open redirects) against a local service.
- **Previews before executing** — every runner defaults to a safe preview.
  Nothing executes, and no network request is sent, until you pass
  `--execute`.
- **Diagnoses from evidence** — parses structured diagnostics (file, line,
  rule, category, verbatim evidence) out of captured stdout/stderr, rather
  than guessing from the exit code alone.
- **Reports honestly** — every result is one of seven explicit states:
  `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`, `NOT_APPLICABLE`, `MANUAL_REVIEW`,
  `UNKNOWN`. A missing tool or a skipped test can never be reported as a
  pass, and the audit's verdict never claims a bare "READY" — the best it
  reports is `READY_WITH_RISKS`, because a clean run is evidence under the
  conditions tested, not a guarantee.
- **Bounds repair, in code, not just in prose** — a 9-step lifecycle caps an
  agent at 3 file-modifying repair attempts per session, separates read-only
  diagnosis (free) from an actual edit (counted), and prohibits deleting
  tests, weakening assertions, or suppressing errors to force a green result.
  `scripts/repair_budget.py` makes the cap a checkable fact: it persists a
  real counter per issue and refuses (exit code 1) past the 4th attempt,
  instead of relying on the agent to self-report honestly.
- **Catches hallucinated and typosquatted dependencies** —
  `scripts/check_dependencies.py` verifies every package declared in
  `requirements*.txt` or `package.json` actually exists on PyPI / npm, and
  flags a package first published under 30 days ago as worth a second look.
  Neither Claude Code nor Codex does this automatically.
- **Redacts credentials** — captured output, HTTP headers, and security
  findings are redacted before they reach a report. A matched secret never
  appears in a report, only its length and a 2-character prefix.

## Verification engines

| Engine | Covers | Script |
| :--- | :--- | :--- |
| **Full audit** | Everything below, combined into one verdict + shareable report | `scripts/run-audit.py` |
| Core runner | test / lint / type-check / build, across detected ecosystems | `scripts/run-checks.py` |
| Security | static scan (26 rules) + opt-in live checks (headers, cookies, auth, IDOR, CSRF, redirects) | `scripts/run-security-tests.py` |
| API | HTTP contract, auth gates, error handling, rate limiting, resilience — against a local loopback service | `scripts/run-api-tests.py` |
| OpenAPI | Validates a live service against an OpenAPI 3.0/3.1 spec (JSON or YAML) | `scripts/run-openapi-tests.py` |
| Browser | 15 Playwright user-journey templates (login, routing, forms, sessions, console errors) | `scripts/run-browser-tests.py` |
| Dependency identity | Verifies declared packages exist on PyPI/npm; flags hallucinated or notably-new names | `scripts/check_dependencies.py` |
| Repair budget | Enforces the 3-attempt repair cap with a real persisted counter, not just a prompt | `scripts/repair_budget.py` |

The static half of the security engine needs no prerequisite at all — it's
read-only, offline, and runs on any project. Live security checks, the API
engine, and the OpenAPI engine target `127.0.0.1`/`localhost` only by default.
Browser checks require Playwright; without it they report `BLOCKED` with
remediation, never a false pass.

There's also a 145-case production-readiness catalog
(`skills/veriflow/references/production-test-catalog.json`) spanning 15
operational categories for risk-based pre-release review, and a
failure-pattern reference
(`skills/veriflow/references/failure-patterns.json`) cataloguing recurring
AI-coding failure modes with their diagnostic signatures and root-cause
hypotheses.

## Requirements

- Python 3.9+. Everything above is pure standard library — no install needed
  to use the core runner, the full audit, the API engine, the OpenAPI engine
  (JSON specs), or the static security scan.
- Optional, each enabling exactly one capability (`pip install -r
  requirements-optional.txt`):
  - `playwright` — browser journeys (plus `python -m playwright install
    chromium`)
  - `PyYAML` — YAML OpenAPI specs (JSON specs need nothing)

## Install

### Claude Code — one command

```text
/plugin marketplace add AdityaWagh06/veriflow
/plugin install veriflow@veriflow
```

That's it. No clone, no copying files — `.claude-plugin/marketplace.json`
points Claude Code straight at this repo's `skills/veriflow/` directory, so
installing and updating are both just a plugin operation. From your shell
instead of inside a session:

```powershell
claude plugin marketplace add AdityaWagh06/veriflow
claude plugin install veriflow@veriflow
```

### Codex, or a manual Claude Code install

Both agents use the same open Agent Skills format — a directory with a
`SKILL.md` describing when to use it — so the same skill content works for
both; only the folder each agent scans for differs:

| | Claude Code scans | Codex scans |
| :--- | :--- | :--- |
| **Project** (this repo only) | `<project>/.claude/skills/` | `<project>/.agents/skills/` |
| **Personal** (every project you open) | `~/.claude/skills/` | `~/.agents/skills/` |

```powershell
git clone https://github.com/AdityaWagh06/veriflow.git
cd veriflow

# Install for BOTH agents at once (default) — costs nothing extra:
python install.py --project

# Or pick just one:
python install.py --project --platform claude      # Claude Code only
python install.py --project --platform codex        # Codex only

# Install for every project you open, instead of just this one:
python install.py --personal

# Confirm it installed correctly:
python install.py --project --verify
```

Use one install method or the other, not both — installing via the plugin
marketplace *and* running `install.py --platform claude` would register the
skill twice.

Then:
- **Claude Code** — restart it, or start a new session, so it rescans skills.
- **Codex** (CLI, IDE extension, or app) — it detects new skills
  automatically; restart only if a newly added skill doesn't appear.

Either way, confirm it loaded by asking: *"what skills do you have
available?"*

The installer never touches a skill directory it didn't create, backs up
anything it would overwrite with `--force`, and is fully reversible with
`--uninstall`. Full detail and troubleshooting: [`INSTALL.md`](INSTALL.md).

## Minimal example

```powershell
# What does this project look like?
python skills/veriflow/scripts/detect-project.py .

# What checks would run? (preview only — nothing executes)
python skills/veriflow/scripts/run-checks.py .

# Actually run them:
python skills/veriflow/scripts/run-checks.py . --execute

# Static security scan — read-only, no setup required:
python skills/veriflow/scripts/run-security-tests.py .
```

Add `--json` to any command for a machine-readable report.

## See it work

This is a real, unedited run against Veriflow's own bundled demo project
(`examples/repair-demo`) — a small app with one intentional bug, used to prove
the toolkit genuinely catches things rather than always saying yes:

```powershell
python skills/veriflow/scripts/run-audit.py examples/repair-demo --execute
```

```
================================================================
Veriflow -- Full Project Audit
================================================================
1. PROJECT
   Ecosystems:      python
   Package manager: unknown

2. STATIC SECURITY SCAN  (read-only, offline, always runs)
   Findings: CRITICAL=0 HIGH=0 MEDIUM=0 LOW=0  (scanned 4 file(s), excluded 0)

3. CORE CHECKS  (1 discovered)
   [PASS] test (python)
   Summary: PASS=1

4. PRODUCTION-READINESS CATALOG SCOPE  (not filtered to this project)
   145 cases across 15 categories available for risk-based manual selection.
   automated_available=79  app_specific_automation=62  manual_review=4
----------------------------------------------------------------
VERDICT: READY_WITH_RISKS
```

And against a deliberately vulnerable file — proving the verdict actually
changes rather than always reporting success:

```
2. STATIC SECURITY SCAN  (read-only, offline, always runs)
   Findings: CRITICAL=2 HIGH=0 MEDIUM=0 LOW=0  (scanned 1 file(s), excluded 0)
     [CRITICAL] SEC-INJ-001    app.py:4   (shell injection via shell=True)
     [CRITICAL] SEC-DESER-001  app.py:7   (unsafe pickle.loads of untrusted data)
----------------------------------------------------------------
VERDICT: NOT_READY
  - 2 CRITICAL static security finding(s).
```

Add `--markdown report.md` to get the same findings as a clean, shareable
Markdown file — useful for pasting into a PR description or handing to a
teammate who wasn't watching the terminal. Every rule and check in Veriflow
carries its own fault-detection test proving it actually fails on the defect
it claims to catch, and passes again once that defect is fixed — this isn't
just an example, it's enforced by the test suite.

## Running the tests

```powershell
pip install -r requirements-dev.txt
python -m pytest tests -q
```

420+ tests. The suite includes fault-injection tests for every security rule
and live check: a deliberately broken fixture proves the check actually fails
on the defect it claims to catch, and a corrected fixture proves it then
passes.

## Limitations

- Security coverage is pattern-based, not a taint analysis — it reduces
  common, detectable issues and is not a penetration test or a substitute for
  one.
- No bundled CVE/vulnerability database. Run your ecosystem's own audit tool
  (`pip-audit`, `npm audit`, `cargo audit`) for dependency vulnerability
  coverage.
- Deep check support (parsed diagnostics, structured failure categories) is
  strongest for Python and JavaScript/TypeScript; other ecosystems get
  project detection but thinner diagnosis.
- Browser checks depend on an optional Playwright install; without it those
  checks are honestly reported `BLOCKED`, not skipped silently.
- The full audit's catalog section is a scope summary of all 145 cases, not a
  per-project filtered result — deciding which cases actually apply still
  needs the judgement call described in `references/production-readiness.md`.

## License

MIT — see [`LICENSE`](LICENSE).

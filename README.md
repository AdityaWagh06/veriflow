# Veriflow

Veriflow helps AI coding agents verify their own work instead of just
claiming it's done. It discovers a project's real checks, runs them safely,
scans for security defects, diagnoses failures from actual evidence, and
reports exactly what passed, what failed, and what it couldn't check — never
a guess dressed up as a pass.

Works as a skill for **Claude Code** and **Codex**.

## Install

**Claude Code** — paste these two lines into a session:

```text
/plugin marketplace add OpenWave-India/veriflow
/plugin install veriflow@veriflow
```

That's the whole install. No cloning, no scripts.

**Codex, or a manual setup** — see [`INSTALL.md`](INSTALL.md) for the
one-command installer (`install.py`), which also covers updating,
uninstalling, and running Veriflow without any agent at all.

## Why this exists

An AI agent can say "all tests pass" without running anything, quietly
weaken a test to make it green, or treat a missing tool as a pass. Veriflow
is built so none of that can happen silently:

- **Discovers real checks** for the project's actual ecosystem (Python,
  JS/TS, Rust, Go, Java, .NET) — without running them until told to.
- **Scans for security defects** — 26 static rules (secrets, injection,
  unsafe deserialization, weak crypto) plus 9 opt-in live checks (headers,
  cookies, auth, IDOR, CSRF), each proven against a real fault it has to
  catch, not just a demo that happens to pass.
- **Catches hallucinated dependencies** — checks every package in
  `requirements.txt` / `package.json` against the real PyPI/npm registry.
- **Reports in seven honest states** — `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`,
  `NOT_APPLICABLE`, `MANUAL_REVIEW`, `UNKNOWN`. A missing tool can never be
  reported as a pass.
- **Enforces its own repair limit** — caps an agent at 3 fix attempts per
  issue with a real persisted counter, not just an instruction it could
  ignore.
- **Redacts secrets** before they ever reach a report.

<details>
<summary><strong>What Claude Code and Codex don't do on their own</strong></summary>

Both are general-purpose agents with shell access — they can run anything
you ask. What neither ships with:

- **A real security scanner.** Ask either to "check for vulnerabilities"
  and you get the model's judgment, no deterministic rules behind it.
- **Dependency identity verification** before you install something an
  agent just suggested.
- **A structural result type.** By default, nothing stops an agent from
  saying "tests pass" when a tool was simply missing.
- **An enforced repair budget**, rather than a promise the agent can break.
- **Output redaction**, so a leaked secret in command output doesn't just
  print straight to your terminal.

What's *not* unique here: preview-before-execute, safe subprocess handling —
an agent could write that itself if asked. The value is that it's already
written, already tested against real faults, and ships as a skill instead of
something you re-explain every session.

</details>

## See it work

A real, unedited run against Veriflow's own demo project — proof it
genuinely catches things, not just a clean report every time:

```powershell
python skills/veriflow/scripts/run-audit.py examples/repair-demo --execute
```

```
2. STATIC SECURITY SCAN  (read-only, offline, always runs)
   Findings: CRITICAL=0 HIGH=0 MEDIUM=0 LOW=0  (scanned 4 file(s))
3. CORE CHECKS  (1 discovered)
   [PASS] test (python)
----------------------------------------------------------------
VERDICT: READY_WITH_RISKS
```

Same command against a file with a real bug planted in it:

```
2. STATIC SECURITY SCAN  (read-only, offline, always runs)
   Findings: CRITICAL=2 HIGH=0 MEDIUM=0 LOW=0  (scanned 1 file(s))
     [CRITICAL] SEC-INJ-001    app.py:4   (shell injection via shell=True)
     [CRITICAL] SEC-DESER-001  app.py:7   (unsafe pickle.loads)
----------------------------------------------------------------
VERDICT: NOT_READY
```

Add `--markdown report.md` for a shareable file instead of terminal output.
Every rule has a test proving it fails on the defect it claims to catch and
passes once that defect is fixed — this isn't a cherry-picked demo, the test
suite enforces it.

## Verification engines

| Engine | Covers |
| :--- | :--- |
| **Full audit** (`run-audit.py`) | Everything below, combined into one verdict |
| Core runner | test / lint / type-check / build |
| Security | 26 static rules + 9 opt-in live checks |
| API / OpenAPI | Contract, auth, error handling — local service only |
| Browser | 15 Playwright user-journey templates |
| Dependency check | Flags hallucinated or brand-new packages |
| Repair budget | Enforces the 3-attempt cap with a real counter |

The static security scan needs no setup at all. Live checks, the API
engine, and the OpenAPI engine only ever target `localhost`. Browser checks
need Playwright; without it, they report `BLOCKED`, never a false pass.

Also included: a 145-case production-readiness catalog and a failure-pattern
reference cataloguing recurring AI-coding mistakes — both in
`skills/veriflow/references/`.

## Requirements

Python 3.9+. Everything above is pure standard library — nothing to install
for the core runner, the audit, the API engine, or the security scan.

Two optional packages, each for one thing only:

| Package | Unlocks | Without it |
| :--- | :--- | :--- |
| `playwright` | Browser journeys | Reports `BLOCKED` |
| `PyYAML` | YAML OpenAPI specs | JSON specs still work |

## Try it

```powershell
python skills/veriflow/scripts/detect-project.py .          # what's here?
python skills/veriflow/scripts/run-checks.py .               # preview only
python skills/veriflow/scripts/run-checks.py . --execute      # actually run
python skills/veriflow/scripts/run-security-tests.py .        # security scan
```

Add `--json` to any command for a machine-readable report.

## Running the tests

```powershell
pip install -r requirements-dev.txt
python -m pytest tests -q
```

480+ tests, including a fault-injection test per security rule proving it
actually detects what it claims to.

## Limitations

- Pattern-based security scanning, not taint analysis — reduces common
  issues, isn't a penetration test.
- No bundled CVE database — run `pip-audit` / `npm audit` / `cargo audit`
  for vulnerability data.
- Deep diagnostics are strongest for Python and JS/TS; other ecosystems get
  detection but thinner diagnosis.
- The audit's catalog section is a scope summary of all 145 cases, not
  filtered to your project — see `references/production-readiness.md`.

## License

MIT — see [`LICENSE`](LICENSE).

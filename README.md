# Veriflow — AI Coding Verification Skill

Veriflow is an open-source verification skill and tool runner designed to help AI coding agents systematically verify code changes after each logical feature batch, diagnose failures honestly, apply minimal repairs within a bounded budget, and re-verify outcomes.

---

## What Veriflow Does

- **Discovers Validation Commands**: Automatically detects project ecosystems (Python, JavaScript/TypeScript, Rust, Go, Java, .NET) and configured test, lint, type-check, and build commands without executing them.
- **Resolves Executables Deterministically**: Prefers project-local virtual environments (`.venv`) and local package tools (`node_modules/.bin`) before falling back to global executables on `PATH`.
- **Safe Opt-In Execution**: Runs checks only when `--execute` is supplied. Executes commands safely with argument lists (`shell=False`) and per-command timeouts.
- **Structured Failure Diagnosis**: Extracts structured diagnostics (`category`, `summary`, `file`, `line`, `rule`, `evidence`) from captured stdout and stderr for Python/pytest tracebacks, ESLint, TypeScript compiler errors, and build tools.
- **Targeted Check Re-Verification**: Enables fast re-verification using `--check <name>` to isolate a single failing check before running the broader suite.
- **Enforces Honest Accounting**: Distinguishes read-only diagnosis from attempted repairs, caps repair attempts at 3, prohibits test weakening or error suppression, and requires post-edit re-execution before claiming success.

---

## Supported Verification Workflow

Veriflow guides the coding agent through a bounded 9-step lifecycle:

```
[1. Discover] -> [2. Preview] -> [3. Execute (Opt-In)] -> [4. Collect Diagnostics]
       |
       v
[5. Analyze Evidence] -> [6. Apply Minimal Fix] -> [7. Rerun Failing Check (--check)]
                                                          |
                                      +-------------------+-------------------+
                                      | (Passed)                              | (Still Failed)
                                      v                                       v
                           [8. Rerun Broader Suite]               [Check Attempt Budget <= 3]
                                      |                                       |
                                      v                                       v
                           [9. Standardized Report]               [Iterate or Stop Early]
```

1. **Discover**: Identify project ecosystems, tools, and commands using `scripts/run-checks.py [target-dir]`.
2. **Preview**: Review discovered checks and rationale in preview mode (default).
3. **Execute**: Run checks only with explicit authorization using `--execute`.
4. **Collect Diagnostics**: Gather structured results (`status`, `diagnostics` array, `stdout`, `stderr`).
5. **Analyze Evidence**: Pinpoint the actionable root cause using verbatim evidence without guessing.
6. **Apply Minimal Fix**: The host AI coding agent applies the smallest reasonable code change using its native editing tools (counts as 1 repair attempt).
7. **Rerun Failing Check**: Re-verify the fix immediately using `--check <name> --execute`.
8. **Rerun Broader Suite**: Run the full project suite by omitting `--check` to catch regressions.
9. **Report**: Emit a standardized completion report distinguishing verified facts from assumptions.

---

## Safety Boundaries & Repair Limits

- **Maximum 3 Repair Attempts**: An agent is capped at 3 file-modifying repair attempts per verification session. Read-only inspection and preview runs never count against the budget.
- **No Test Weakening**: Never delete tests, remove assertions, or disable linter rules (`# noqa`, `// eslint-disable`) to fake passing status.
- **No Speculative Churn**: Stop immediately if evidence is ambiguous, the failure is pre-existing, or fixes would be speculative.
- **Reversion on Regression**: Revert targeted edits if an attempt introduces new failures or breaks other checks.
- **Separation of Concerns**: `run-checks.py` is strictly a verification runner and diagnostic parser. It contains no automatic code editing or self-modification logic. The host AI agent performs all edits.
- **Safety Notice**: Passing verification tests confirms that executed checks succeeded under test conditions; it does not guarantee zero defects, complete security, or deployment readiness.

---

## Usage

### Preview Mode (Default)
Preview available checks and resolved executables without running any commands:
```bash
python skills/veriflow/scripts/run-checks.py [project-dir]
```

### Execution Mode
Explicitly execute discovered checks:
```bash
python skills/veriflow/scripts/run-checks.py [project-dir] --execute
```

### Filter a Specific Check
Preview or execute a single check by name:
```bash
# Preview only the test check:
python skills/veriflow/scripts/run-checks.py [project-dir] --check test

# Execute only the test check:
python skills/veriflow/scripts/run-checks.py [project-dir] --check test --execute
```

### Structured JSON Output
Add `--json` for machine-readable JSON execution reports:
```bash
python skills/veriflow/scripts/run-checks.py [project-dir] --execute --json
```

---

## End-to-End Repair Demonstration

A reproducible, documented example of an end-to-end diagnostic and repair session is preserved in [`examples/repair-demo/`](examples/repair-demo/):
- **Problem**: Incorrect arithmetic in discount calculation (`+` instead of `-`).
- **Diagnosis**: Pytest failure automatically classified as `TEST_ASSERTION_FAILURE` with evidence `assert 120.0 == 80.0`.
- **Repair**: Single targeted line change in application code without touching the test.
- **Verification**: Immediate pass via `--check test --execute` followed by full suite pass.

See [`examples/repair-demo/README.md`](examples/repair-demo/README.md) for full details and reproduction instructions.

---

## Running the Veriflow Test Suite

Run Veriflow's test suite using Python's standard library `unittest` or `pytest`:

```bash
# Standard library test runner:
python -m unittest discover tests -v

# Pytest runner:
pytest tests -v
```

All 68 tests validate project detection, check discovery, execution safety, Windows launchers, local tool discovery, diagnostic parsing, bounded repair specifications, and `--check` filtering.

---

## Known Limitations

- **Host Agent Integration**: Veriflow provides guidance and scripts; integration depends on the host coding agent's skill invocation capabilities unless external hooks are configured.
- **Pre-Existing Failures**: The runner does not inspect Git blame or commit history; pre-existing vs. introduced failures must be triaged by the agent inspecting `git status` / `git diff`.
- **Custom Test Formats**: Non-standard or proprietary test runners emitting unrecognizable output are classified under `UNCLASSIFIED` with raw stdout/stderr preserved for manual agent review.
# Veriflow Repair Workflow Reference

The bounded, evidence-driven repair lifecycle Veriflow requires when a check
fails. Read this when a verification check has failed and you are about to
change code.

`SKILL.md` carries the summary; this file is the authoritative detail for the
nine steps, the attempt budget, the failure triage table, and the boundary
between the runner and the editing agent.

---

### 5. Bounded AI-Guided Repair and Re-Verification Lifecycle

When one or more executed checks fail, follow this structured, bounded 9-step lifecycle:

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

#### Step 1: Discover Project Checks
Run `run-checks.py [target-project-dir]` to identify project ecosystems, configuration markers, and discoverable validation commands.

#### Step 2: Show Planned Checks (Preview)
Present the discovered commands, resolved executables, and rationale to the user or conversation log before executing anything. Explain what each check validates (tests, formatting, linting, type-checking, or build). You may preview a single check using `--check <name>`.

#### Step 3: Execute Only When Explicitly Authorized
Execute checks only when the user or operational task explicitly requests execution by passing `--execute`:
```bash
python <path-to-skill>/scripts/run-checks.py [target-project-dir] --execute
```
Never execute commands during discovery preview mode.

#### Step 4: Collect Results and Structured Diagnostics
Collect the execution results and inspect the structured `diagnostics` array for each failing or anomalous check (`FAIL`, `TIMEOUT`, `COMMAND_NOT_FOUND`, `ERROR`). Note parsed `category`, `summary`, `file`, `line`, `column`, `rule`, and verbatim `evidence`.

#### Step 5: Analyze Evidence and Identify Root Cause
Analyze the parsed evidence and captured `stdout` and `stderr` to determine the most probable actionable root cause.
- Trace the failure back to recent modifications or touched call sites.
- Clearly distinguish **parsed evidence** (actual compiler/test output) from **inferred explanations** (agent hypothesis).
- Never guess or invent causes when output is insufficient.

#### Step 6: Propose or Apply the Smallest Reasonable Code Change
If evidence is sufficient, actionable, and directly relates to the current task:
- Apply the smallest reasonable, targeted change using the host coding agent's normal editing tools (e.g. `replace_file_content`).
- Respect user permissions and approvals; do not bypass tool boundaries.
- **This file modification counts as 1 repair attempt.**

#### Step 7: Rerun the Relevant Failing Check
Immediately rerun only the specific check that failed by providing its exact discovered check name with `--check`:
```bash
python <path-to-skill>/scripts/run-checks.py [target-project-dir] --check <failing-check-name> --execute
```
Using `--check <name>` (such as `test`, `typecheck`, or `build`) ensures fast feedback on the targeted fix while preventing accidental execution of unselected checks. Do not assume an edit solved the issue without re-executing the check.

#### Step 8: Rerun Broader Verification Suite
Once the failing check passes via `--check <name>`, rerun the broader verification suite across the whole project by omitting `--check`:
```bash
python <path-to-skill>/scripts/run-checks.py [target-project-dir] --execute
```
This confirms that the targeted repair did not introduce regressions in other parts of the project.

#### Step 9: Report Final Results
Produce a complete, honest completion report distinguishing verified facts, attempted fixes, remaining limitations, and unresolved issues.

---

### Repair Lifecycle Distinctions

To ensure honest accounting, maintain clear boundaries between the three stages of repair:

| Stage | Definition | Counts Toward Attempt Budget? |
| :--- | :--- | :--- |
| **Diagnosis** | Reading error output, analyzing tracebacks, inspecting files, identifying root causes, and triaging errors without altering code. | **No** (0 attempts) |
| **Attempted Repair** | Applying any modification to project files in an effort to resolve a check failure. | **Yes** (1 attempt per file modification batch) |
| **Verified Repair** | Confirmation through actual re-execution of the check *after* the modification that the check now produces `PASS` without introducing regressions. | N/A (Confirmed outcome) |

> [!IMPORTANT]
> Never report that a repair succeeded merely because an edit was made or a diagnostic was generated. A repair is only verified when the check actually passes upon re-execution.

---

### Strict Repair Limits & Early Stop Rules

1. **Maximum 3 Repair Attempts**:
   - An agent is strictly allowed a maximum of **3 repair attempts** per verification session.
   - An attempt is counted **only when the agent modifies project files** in response to a failure.
   - Read-only investigation, log inspection, and running preview checks never count against the budget.
2. **Never Repeat Unsuccessful Fixes**:
   - Never apply the same or essentially identical unsuccessful fix twice. Every new attempt must be backed by distinct diagnostic evidence or a different hypothesis.
3. **Immediate Re-Verification**:
   - After each repair attempt, immediately rerun the relevant check using `--check <failing-check-name> --execute` before taking any further action or modifying any additional files.
4. **Early Stop Conditions**:
   Stop repair attempts immediately and report findings to the user if:
   - The diagnostic evidence is ambiguous, incomplete, or insufficient to identify root cause.
   - The failure appears unrelated to recent changes (e.g., pre-existing broken tests or missing system tools).
   - Further edits would be speculative ("shotgun debugging").
   - A repair attempt introduces unexpected regressions or cascading failures across other checks.
5. **Regression Reversion**:
   - If a repair attempt breaks previously passing checks or worsens failures, report the regression honestly.
   - If safe and supported by the agent's editing tools, revert the agent's targeted modification to restore the project to its prior state before stopping.
6. **Code & Test Integrity Prohibitions**:
   - **Never delete or weaken tests**: Do not remove test cases, comment out assertions, or reduce assertion strictness solely to obtain a passing result.
   - **Never disable linter or type-checker rules**: Do not insert suppression directives (e.g. `# noqa`, `// eslint-disable`, `@ts-ignore`, `# type: ignore`) or delete configuration rules to bypass violations.
   - **Never suppress errors**: Do not swallow exceptions (e.g. `catch (e) {}` or `except: pass`) to hide failures.
   - **Never alter project configuration arbitrarily**: Do not modify dependencies, lockfiles, package manifests (`package.json`, `pyproject.toml`, `Cargo.toml`), or security policies unless the diagnosis specifically and definitively justifies it.

---

### Triage by Failure Category

Handle failures according to their structured diagnostic classification:

#### 1. Recognized Source-Code Errors (`TEST_ASSERTION_FAILURE`, `PYTHON_TRACEBACK`, `SYNTAX_ERROR`, `LINT_VIOLATION`, `TYPE_ERROR`, `BUILD_ERROR`)
- **Evidence**: Specific file paths, line/column numbers, error codes, and assertion details are present.
- **Action**: Locate the referenced coordinates in recent edits. Diagnose why the symbol, syntax, type, or assertion failed. Apply a minimal, targeted correction and rerun the check.

#### 2. Unclassified Failures (`UNCLASSIFIED`)
- **Evidence**: Process returned a non-zero exit code or empty stderr, and stdout/stderr did not match known compiler, test, or linter signatures.
- **Action**: **Do not guess or hallucinate explanations.** Inspect raw stdout and stderr in context. If the failure cannot be attributed with high confidence to recent code changes, **stop immediately**. Report the raw evidence and outline recommended manual diagnostic steps.

#### 3. Missing Tools or Commands (`COMMAND_NOT_FOUND`)
- **Evidence**: Discovered tool (e.g. `pytest`, `eslint`, `tsc`, `cargo`) is not installed on PATH or in the project environment.
- **Action**:
  - Report the tool as missing under limitations and mark status as `COMMAND_NOT_FOUND`.
  - **Do not modify source code** to bypass or mock the missing tool.
  - **Do not automatically install packages** or run system package managers without explicit user authorization.

#### 4. Timeouts (`TIMEOUT`)
- **Evidence**: Command process exceeded the per-command timeout (default 30 seconds).
- **Action**:
  - Inspect recent changes for infinite loops, recursive calls without base cases, hanging network requests, or deadlocks.
  - If recent changes introduced a blocking condition, apply a targeted fix.
  - If the test suite is simply large or legitimately slow, explain this to the user and suggest running with `--timeout <higher_seconds>`. Do not rewrite valid application logic merely to race against the timeout.

#### 5. Environment and Dependency Issues (`IMPORT_OR_MODULE_ERROR`, missing native binaries)
- **Evidence**: `ModuleNotFoundError`, `Cannot find module`, or missing shared libraries.
- **Action**: Report the missing dependency clearly. Do not automatically invoke `pip install`, `npm install`, or download files from the network during verification.

#### 6. Pre-Existing Failures
- **Evidence**: Failure occurs in files, modules, or test suites untouched by the current feature batch, or present in the repository prior to the agent's work.
- **Action**: Check `git status` / `git diff` to verify the failure is outside current scope. Do not perform wide-ranging refactors on untouched code. Document the pre-existing failure in the completion report for user visibility.

#### Operational Safety Boundaries
During diagnosis and repair, the agent must **never**:
- Access, log, or expose secret keys, API credentials, or environment tokens.
- Modify environment variables or system configuration files.
- Make arbitrary or unapproved network requests.

---

### Separation of Runner and Editing Responsibilities

To maintain modularity and safety:
1. **Verification Runner (`run-checks.py`)**:
   - Strictly responsible for check discovery, executable resolution, safe process execution (`shell=False`), output capture, and structured diagnostic parsing.
   - Remains **preview-only by default** and executes checks **only** when `--execute` is passed.
   - Contains **no automatic file modification logic**, self-repair capabilities, or hidden subprocesses.
2. **Host AI Coding Agent**:
   - Analyzes the structured results and diagnostics emitted by the runner.
   - Uses its own native file-editing tools (e.g. `replace_file_content`, file editors) to make authorized, minimal changes.
   - Strictly obeys user approval and environment permissions. Never bypasses user prompts or tool safeguards.

---

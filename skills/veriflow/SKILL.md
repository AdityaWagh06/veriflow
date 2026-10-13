---
name: veriflow
description: Verify AI-generated code changes by running relevant project checks, diagnosing failures, applying minimal fixes, and confirming results. Use when implementing features, modifying existing code, fixing bugs, or preparing a project for release.
---

# Veriflow — AI Coding Verification Skill

## Purpose

Do not treat code as complete merely because it has been written.

Verify that changes work, preserve existing behavior, and meet the project's established quality standards.

## Invocation and Architecture

Veriflow provides structured verification guidance accompanied by automation scripts located within the skill directory:

- **Project Detector**: `scripts/detect-project.py`
  Discovers project ecosystems (Python, JavaScript, TypeScript, Rust, Go, .NET), package managers, and configured npm/project scripts.
- **Verification Runner**: `scripts/run-checks.py`
  Discovers available validation commands from project configurations (preview by default) and optionally executes them via `--execute`.
- **Reference Checklist**: `references/verification-checklist.md`
  Detailed checklist for change reviews, routing, security, and release readiness.

> **Note on Agent Integration**:
> Coding agents and automation environments do not all trigger skills automatically. Agents and developers must invoke these scripts explicitly when verifying changes, unless an external runner or hook has been configured. Always reference scripts relative to the installed skill directory.

---

## Core Workflow

Before starting the workflow, read `references/verification-checklist.md`. Apply only the checks relevant to the current project and changes.

Follow this workflow whenever implementing a feature, fixing a bug, or modifying existing code.

### 1. Inspect Before Changing

1. **Inspect project instructions and Git status**:
   - Read relevant project instructions (`AGENTS.md`, `README.md`, contributor guidelines).
   - Inspect the working tree (`git status`, `git diff`) to identify existing user work. Never overwrite or discard unrelated changes.
2. **Run project detection**:
   Invoke the detection script on the target project directory:
   ```bash
   python <path-to-skill>/scripts/detect-project.py [target-project-dir]
   ```
   Inspect the output for identified languages, frameworks, package managers, and defined package scripts.

### 2. Plan a Small Feature Batch

- Break work into small, logically complete feature batches.
- Identify affected files and likely regression risks.
- Define what checks must pass before declaring the batch complete.
- Prefer focused changes over wide-ranging refactors.

### 3. Implement Focused Changes

- Follow existing naming, architectural, and error-handling patterns.
- Avoid unrelated refactoring or changing unrequested files.
- Handle expected errors and edge cases defensively.
- Never hardcode credentials, secrets, or API keys.
- Never weaken security controls or test assertions simply to make checks pass.

### 4. Verify After Each Logical Feature Batch

Verification follows a two-stage approach: **Discovery Preview** followed by **Explicit Execution**.

#### Stage 4A: Run Discovery Preview
Always preview available checks before running commands:
```bash
python <path-to-skill>/scripts/run-checks.py [target-project-dir]
```
Add `--json` for machine-readable output:
```bash
python <path-to-skill>/scripts/run-checks.py [target-project-dir] --json
```
- Review the proposed checks, resolved executables, and discovery rationale (e.g., pytest, ruff, mypy, npm scripts, cargo test).
- Inspect the resolution source:
  1. **Project Virtual Environment** (`.venv`, `venv`, `env`): Python tools preferred via `python -m <tool>`.
  2. **Project Node Modules** (`node_modules/.bin`): Local ESLint, TypeScript (`tsc`), etc.
  3. **Project Root Scripts**: Direct project wrappers (e.g. `gradlew.bat`, `mvnw`).
  4. **System PATH**: Global executables via `shutil.which` when project-local tools are absent.
  5. **Not Found**: Unresolved tools reported in limitations and evaluated as `COMMAND_NOT_FOUND` on execution.
- Review listed limitations (e.g., missing linters or absent test suites).
- Never assume an unlisted check exists or that an absent tool is installed.

#### Stage 4B: Execute Relevant Checks Explicitly
Execute the discovered validation commands using the `--execute` flag:
```bash
python <path-to-skill>/scripts/run-checks.py [target-project-dir] --execute
```
Optional flags:
- `--timeout SECONDS`: Set a custom per-command timeout (default: 30 seconds).
- `--check NAME`: Filter to preview or execute only the specified check name (matches the exact discovered check name, such as `test`, `lint`, `typecheck`, `build`, or a package script name).
- `--json`: Emit a structured execution report with stdout, stderr, exit codes, and parsed `diagnostics`.

The runner evaluates each command safely without shell strings (`shell=False`), tracks process duration, and classifies outcomes into:
- `PASS`: Process exited successfully with code 0.
- `FAIL`: Process exited with a non-zero code.
- `TIMEOUT`: Process exceeded the per-command execution timeout.
- `COMMAND_NOT_FOUND`: Executable is not installed on PATH or in the project.
- `ERROR`: Operating system or execution error.

Each failing or anomalous check includes a structured `diagnostics` array containing extracted error locations, rule IDs, and verbatim evidence.

If the user requested multiple feature batches, verify each batch before moving to the next.

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

### 6. Check Integrations and Routing

When applicable:
- Confirm frontend routes point to valid components and handlers.
- Verify API paths, HTTP methods, request payloads, and status codes.
- Validate authentication and authorization boundaries on protected endpoints.
- Check loading, empty, success, and error states in user-facing components.

### 7. Review Security and Dependencies

- Check input validation and output encoding where appropriate.
- Scan for exposed secrets, unsafe command concatenation, or injection risks.
- Never install dependencies automatically without a clear reason and authorization.
- Never print secrets into logs, outputs, or completion reports.

### 8. Final Verification & Completion Report

Before declaring work complete:
- Inspect `git diff` for accidental modifications or stray files.
- Rerun relevant checks after the final code edit.
- Provide a standardized completion report distinguishing verified facts from assumptions.

---

## Safety Rules

- Preserve user data and unrelated modifications.
- Never execute arbitrary, unreviewed shell scripts.
- Always use argument lists rather than concatenated shell strings.
- Never claim zero bugs, complete security, or guaranteed deployment success. A passing check suite verifies only that executed tests and checks succeeded under test conditions.
- Do not claim a check passed unless you actually ran it and inspected its outcome.
- If a check was not run or a command was missing, report it as `NOT RUN` or `COMMAND_NOT_FOUND`.
- Cap repair attempts at 3. Stop early on ambiguous evidence or pre-existing issues.
- Never delete tests, weaken assertions, disable linter rules, or suppress errors to simulate success.

---

## Standardized Completion Report Format

After completing verification and any bounded repairs, provide this standardized report:

```markdown
### Changes Summary
- Brief description of the features or modifications implemented.

### Checks Discovered
- Discovered checks with resolved tools, rationale, and configuration markers.

### Checks Executed & Statuses
- [PASS] <check name> (<ecosystem>): executed via run-checks.py --execute (<duration>s)
- [FAIL] <check name> (<ecosystem>): error summary (<duration>s)
- [TIMEOUT] <check name> (<ecosystem>): timed out after <N>s
- [COMMAND_NOT_FOUND] <tool>: missing from PATH or project environment
- [NOT_RUN] <check name>: explanation of why discovery preview only or skipped

### Diagnosed Failures & Evidence
- List each diagnosed failure:
  - Check: <name>
  - Category: <category>
  - Location: <file>:<line>:<col> (if known)
  - Rule: <rule> (if applicable)
  - Summary: <concise summary>
  - Evidence: `<verbatim snippet>`

### Files Changed by Agent
- List of files modified during implementation and repairs:
  - `path/to/file1.ext`
  - `path/to/file2.ext`

### Repair Attempts
- Total attempts used: X / 3
- Attempt 1: <Description of minimal change made and rationale> -> Outcome: <PASS/FAIL>
- Attempt 2 (if needed): <Description of change> -> Outcome: <PASS/FAIL>
- Attempt 3 (if needed): <Description of change> -> Outcome: <PASS/FAIL>
*(Or: "No repairs required; all checks passed on initial run.")*

### Checks Rerun After Repairs
- List of checks re-executed after code changes and their outcomes.

### Final Verification Status
- Status: VERIFIED | PARTIALLY_VERIFIED | UNRESOLVED
- Summary of final test, lint, and build state.

### Remaining Risks, Uncertainties & Limitations
- Unverified edge cases, skipped checks, missing tools, or pre-existing failures.

### Safety Notice
- Verification confirms that executed checks passed under current environment conditions. It does not guarantee zero defects, complete security, or deployment readiness.

### Recommended Next Step
- The single most logical next action for the user or development team.
```
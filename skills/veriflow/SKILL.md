---
name: veriflow
description: Verify AI-generated code changes by running relevant project checks, diagnosing failures, applying minimal fixes, and confirming results. Use when implementing features, modifying existing code, fixing bugs, or preparing a project for release.
---

# Veriflow — AI Coding Verification Skill

## Purpose

Do not treat code as complete merely because it has been written.

Verify that changes work, preserve existing behavior, and meet the project's established quality standards.

## Invocation and Architecture

Veriflow provides structured verification guidance accompanied by automation scripts and references located within the skill directory:

- **Project Detector**: `scripts/detect-project.py`
  Discovers project ecosystems (Python, JavaScript, TypeScript, Rust, Go, .NET), package managers, and configured npm/project scripts.
- **Verification Runner**: `scripts/run-checks.py`
  Discovers available validation commands from project configurations (preview by default) and optionally executes them via `--execute`.
- **Reference Checklist**: `references/verification-checklist.md`
  Detailed checklist for change reviews, failure triage, routing, security, and release readiness.
- **Production-Readiness Test Catalog**: `references/production-test-catalog.json`
  Machine-readable catalog of 135+ research-backed production test cases across 15 critical operational categories.
- **Catalog Reference Guide**: `references/production-test-catalog-guide.md`
  Schema definitions, category guidelines, applicability rules, severity scales, automation tiers, and maintenance instructions.

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

## Production-Readiness Verification Workflow

When preparing an AI-built website or web application for production release, expand beyond routine code checks into a research-backed, risk-based production-readiness review using the **Production-Readiness Test Catalog** (`references/production-test-catalog.json`).

AI coding agents often generate applications that appear complete on the surface but harbor broken user journeys, brittle routing, vulnerable authentication, missing error boundaries, security gaps, fragile third-party integrations, and capacity bottlenecks. Veriflow helps agents systematically identify, triage, and verify these risks.

### 1. Inspect Application Architecture and Critical Journeys

Before selecting tests or evaluating readiness:
1. **Inspect Application Surface**:
   - Detect tech stack, package managers, and toolchain (`scripts/detect-project.py`).
   - Identify defined frontend and backend routes, API controllers, and middleware.
   - Map user roles (e.g., anonymous visitor, standard user, administrator, organization owner).
   - Inspect data models, persistence layers (database, caches, local storage), and external third-party dependencies (auth providers, payment gateways, email services).
   - Review existing test coverage across unit, integration, and end-to-end suites.
2. **Map Critical User Journeys (CUJs)**:
   - Trace the highest-value end-to-end workflows:
     - Onboarding & Identity: Registration -> Verification -> Login -> Session Persistence -> Logout.
     - Primary Transaction: Browse -> Search/Filter -> Create/Update Record -> Submit Transaction -> Confirmation.
     - Administrative & Privileged: Role-gated settings -> Sensitive mutations -> Audit logging.
     - Recovery Paths: Password reset -> Session expiry -> 404 navigation -> Network reconnection.

### 2. Risk-Based Catalog Selection and Applicability

Never blindly execute or require every test in the catalog. Filter `references/production-test-catalog.json` by matching applicability conditions against the application's actual architecture:

- **Explicit Applicability Rules**:
  - Do NOT require OAuth or multi-factor authentication if the app only uses password credentials.
  - Do NOT test payment flows, subscription handling, or webhooks if the app has no billing system.
  - Do NOT require multi-tenant isolation or role escalation checks if the app is single-tenant or single-role.
  - Do NOT test background worker saturation or queue buildup if no async worker queue exists.
  - If a catalog test is not applicable, mark it explicitly as `NOT_APPLICABLE` with the reason.
- **Distinguish Automation Tiers**:
  - `automated_available` (Currently Executable): Tests executable today using standard tooling, static analyzers, linters, unit test runners, or HTTP probes via `scripts/run-checks.py`.
  - `app_specific_automation` (Requires App Scripts): Tests that require application-specific test scripts (e.g. Playwright browser specs, mock server fixtures, database seeding).
  - `manual_review` (Requires Human/Manual Assessment): Tests that require human domain expertise, architectural threat modeling, physical assistive technology verification, or disaster recovery drills.
- **Truth in Reporting**:
  - Distinguish what is actually executable today from what is planned for automation or documented as a manual check. Never claim a catalog test was executed unless it was actually run.

### 3. Verify Real Behavior vs Shallow Presence

A passing component build or the mere existence of a route file does **not** prove functional correctness. The agent must verify actual runtime behavior:

- **Full Journey Tracing for Authentication**:
  - When verifying authentication (`AUTH` category), trace the entire end-to-end lifecycle:
    1. Form submission with valid credentials ->
    2. API response and cookie/token handling ->
    3. Session state established ->
    4. Client-side navigation / redirect to originally requested destination (`returnUrl`) ->
    5. Protected page rendered with authenticated state ->
    6. Browser refresh retains authenticated state ->
    7. Logout invalidates session tokens on both client and server ->
    8. Direct navigation to protected route after logout is rejected and redirected to login.
- **No Inventing Expected Behavior**:
  - Never guess or silently hallucinate expected product behavior or business rules.
  - If business logic, redirect destinations, or authorization requirements are ambiguous in the codebase or specifications, mark the test as `UNKNOWN` or requiring clarification rather than making assumptions.

### 4. Performance, Scalability & Capacity Planning (100k Users Requirement)

- **Clarify the 100k Requirement**:
  - Treat "100,000 users" as an architectural capacity-planning and modeling requirement, **never** as a universal test default.
  - Explicitly distinguish between:
    - *100,000 registered users* (database sizing, indexing, pagination, search scalability).
    - *100,000 total daily visits* (average ~1.15 requests per second; cache hit ratios).
    - *100,000 concurrent active connections* (WebSocket / HTTP connection limits, thread/event-loop architecture, memory footprint).
    - *Specific requests-per-second (RPS) peak workload* (load profile, database connection pools, downstream rate limits).
- **No False Claims**:
  - **Never** claim an application supports 100,000 users based only on a passing unit test, local smoke test, or single-user dev server run.
- **Load Testing Safety Boundaries**:
  - Load, stress, spike, and endurance tests must execute only in an **explicitly authorized, isolated staging environment**.
  - Never launch high-volume traffic or stress tests against production environments or third-party SaaS services without explicit authorization.
  - Before running load tests, define: target traffic (RPS), duration, ramp-up schedule, acceptable latency thresholds (p95/p99), error budget (<0.1%), and monitoring metrics.

### 5. Explicit 7-State Result Standardization

Standardize every evaluated check and catalog item into one of seven explicit states. Never treat a missing test, skipped check, or unavailable tool as a pass:

| Result State | Definition | Criteria |
| :--- | :--- | :--- |
| `PASS` | Executed and Passed | Check or test was executed with explicit authorization; process exited with code 0; assertions and expected behavior verified. |
| `FAIL` | Executed and Failed | Check or test was executed and failed; assertions failed, process returned non-zero code, or diagnostic errors detected. |
| `BLOCKED` | Blocked by Environment | Cannot execute because a required dependency, environment variable, database, credential, or tool is unavailable. |
| `NOT_RUN` | Not Executed | Identified or planned, but not executed in the current session (e.g. preview mode or scope boundary). |
| `NOT_APPLICABLE` | Not Applicable | Irrelevant to this application based on documented applicability rules (e.g. no OAuth, no billing). Must include reason. |
| `MANUAL_REVIEW` | Requires Human Review | Requires qualitative human assessment, physical screen-reader verification, or architectural threat evaluation. |
| `UNKNOWN` | Inconclusive Evidence | Insufficient output, ambiguous logs, or uncertain process outcome. Requires investigation before making claims. |

### 6. Pre-Deployment vs Post-Deployment Verification Gates

- **Pre-Deployment Verification**:
  1. Run safe static checks (linters, formatters, type-checkers).
  2. Run existing automated test suites (unit, component, contract tests).
  3. Validate production build (`npm run build`, `cargo build --release`, etc.).
  4. Select and execute applicable pre-deployment catalog cases (`execution_phase: pre_deployment` or `both`).
  5. Apply bounded repairs (maximum 3 attempts) for any newly introduced regressions.
  6. Produce a Pre-Deployment Production Readiness Report and flag any blocking risks.
- **Post-Deployment Verification**:
  1. Run **only authorized, non-destructive smoke checks** (`execution_phase: post_deployment` or `both`) against the deployed URL.
  2. Verify core user journeys: homepage loads, health probe returns HTTP 200, public routes render without JavaScript exceptions, authentication login/logout functions.
  3. Verify security headers, TLS certificate validity, and absence of exposed debug traces.
  4. Monitor error telemetry, latency percentiles, and request logs for elevated error spikes.
  5. Do **not** run destructive security tests, stress tests, or simulate infrastructure failures against production without explicit operational authorization.

### 7. Grounding in Established Technical References

All production test cases and verification guidelines are grounded in established industry standards:
- **OWASP Authentication Cheat Sheet**: [https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- **OWASP Session Management Cheat Sheet**: [https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- **OWASP Authorization Cheat Sheet**: [https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- **OWASP Web Security Testing Guide (WSTG)**: [https://owasp.org/www-project-web-security-testing-guide/](https://owasp.org/www-project-web-security-testing-guide/)
- **Playwright Authentication Testing**: [https://playwright.dev/docs/auth](https://playwright.dev/docs/auth)
- **Playwright Network Testing**: [https://playwright.dev/docs/network](https://playwright.dev/docs/network)
- **Google web.dev Core Web Vitals**: [https://web.dev/articles/vitals](https://web.dev/articles/vitals)
- **Google SRE Launch Checklist**: [https://sre.google/sre-book/launch-checklist/](https://sre.google/sre-book/launch-checklist/)

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

---

## Production Readiness Assessment Report Format

When performing a comprehensive production-readiness verification session (e.g., prior to deployment or release review), provide this structured assessment report:

```markdown
# Production Readiness Assessment Report

## 1. Executive Summary & Release Verdict
- **Application Name / Target**: <Target project or application name>
- **Environment**: <Local preview | Staging | Production URL>
- **Readiness Verdict**: READY | NOT_READY | READY_WITH_ACCEPTED_RISKS
- **Summary**: Concise high-level summary of verification findings and release posture.

## 2. Test Selection & Execution Metrics
- **Catalog Cases Evaluated**: <Total evaluated out of 135>
- **Results Breakdown**:
  - `PASS`: <count> (Executed and verified)
  - `FAIL`: <count> (Executed and failed)
  - `BLOCKED`: <count> (Blocked by missing dependency/credential/environment)
  - `NOT_RUN`: <count> (Discovered/planned, but not executed)
  - `NOT_APPLICABLE`: <count> (Irrelevant to this architecture, with reason)
  - `MANUAL_REVIEW`: <count> (Requires qualitative human evaluation)
  - `UNKNOWN`: <count> (Inconclusive evidence)
- **Automation Execution Tiers**:
  - `automated_available`: <count> executed via Veriflow runner / CLI
  - `app_specific_automation`: <count> automated via custom app scripts
  - `manual_review`: <count> documented for human inspection

## 3. Critical User Journeys Covered
- [x] Onboarding & Authentication: <Status and evidence>
- [x] Primary Business Transaction: <Status and evidence>
- [x] Routing & Navigation: <Status and evidence>
- [x] Authorization & Access Control: <Status and evidence>
- [x] Recovery & Error Boundaries: <Status and evidence>

## 4. Security Findings & Severity
- **Critical / High Severity**: <Findings or "None identified">
- **Medium / Low Severity**: <Findings or "None identified">
- **OWASP Guidance Alignment**: Input reflection (XSS), SQL/NoSQL injection, CSRF, IDOR, sensitive cookie flags, secret scanning in bundles.

## 5. Performance & Capacity Planning (Workload & Environment)
- **Evaluation Type**: <Measured Benchmark | Architectural Capacity Model>
- **Workload Definition**:
  - Target Concurrency: <N concurrent users>
  - Target Request Rate: <N requests per second>
  - Total Registered User Capacity Target: <e.g., 100,000 registered users model>
- **Measured Metrics (if executed)**:
  - p95 Latency: <ms>
  - p99 Latency: <ms>
  - Error Rate: <percentage>
- **Capacity Observations & Bottlenecks**: Database connection pooling, bundle size, DOM depth, memory profile.

## 6. Deployment & Configuration Checks
- [ ] Production build succeeds without warnings (`build`)
- [ ] Environment variables validated and secrets excluded from repository
- [ ] Database migrations tested for idempotency and rollback safety
- [ ] HTTPS and secure cookie flags (`Secure`, `HttpOnly`, `SameSite`) verified
- [ ] Health probe (`/health`, `/ready`) operational

## 7. Known Risks, Blocked Tests & Unresolved Questions
- **Blocked Tests**: <List tests blocked by missing external dependencies or credentials>
- **Unresolved Business Logic**: <Ambiguous product behaviors requiring stakeholder clarification>
- **Known Technical Debt**: <Non-blocking issues documented for post-release tracking>

## 8. Supporting Evidence
- `<Verbatim log snippet, HTTP response, or test runner output>`

## 9. Safety & Limitations Notice
- Production readiness verification evaluates application behavior against executed test cases under test conditions. It does not promise zero errors or guarantee performance under untested traffic patterns.
```
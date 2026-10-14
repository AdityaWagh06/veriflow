# Veriflow Verification Checklist

Use this checklist after implementing a feature or fixing a bug.

## 1. Change Review

- [ ] Inspect the changed files and relevant diffs.
- [ ] Check for accidental changes or unrelated refactoring.
- [ ] Check imports, exports, and references to renamed symbols.
- [ ] Confirm the implementation follows existing project conventions.

## 2. Code Quality

- [ ] Run the project's existing formatter or formatting check.
- [ ] Run the project's linter.
- [ ] Run type checking or compilation when available.
- [ ] Review warnings and errors rather than ignoring them.

## 3. Functional Testing

- [ ] Run tests relevant to the changed functionality.
- [ ] Test expected behavior and important edge cases.
- [ ] Check error handling and invalid inputs.
- [ ] Run related regression tests.

## 4. Failure Triage and Bounded Repair

When checks fail during execution:

- [ ] **Inspect Diagnostics First**: Review structured `diagnostics` (category, summary, file/line coordinates, and verbatim evidence) before proposing edits.
- [ ] **Track Repair Budget**: Count at most 3 repair attempts per session. Count only file modifications made in response to failures (read-only diagnosis does not count).
- [ ] **Apply Minimal, Targeted Fixes**: Address the specific identified root cause without making unrequested refactors.
- [ ] **Never Repeat Unsuccessful Fixes**: Ensure each attempt is based on distinct evidence or a new hypothesis.
- [ ] **Re-Verify Immediately**: Rerun the relevant failing check using `--check <failing-check-name> --execute` immediately after modifying files. Never declare a repair successful without re-execution.
- [ ] **Rerun Broader Suite**: Rerun all project checks (omitting `--check`) after the failing check passes to detect regressions across other components.
- [ ] **Stop Early on Uncertainty**: If evidence is ambiguous, failures are pre-existing, or fixes would be speculative, stop and report findings.
- [ ] **Handle Non-Code Failures Appropriately**:
  - `UNCLASSIFIED`: Do not guess; inspect raw output; stop if root cause is unclear.
  - `COMMAND_NOT_FOUND`: Report missing tool; do not bypass in code or auto-install tools.
  - `TIMEOUT`: Check for infinite loops; suggest higher timeout if test is legitimately slow.
  - Missing dependencies: Report missing module; do not run unauthorized package managers.
- [ ] **Enforce Code Integrity Prohibitions**:
  - Do NOT delete or weaken failing tests or assertions.
  - Do NOT add suppression comments (`# noqa`, `// eslint-disable`, `@ts-ignore`).
  - Do NOT catch and silence exceptions to fake success.
  - Do NOT modify dependencies or configuration unless strictly justified.
- [ ] **Regression Reversion**: If a repair introduces regressions, report them honestly and revert the agent's targeted edit if safe.

## 5. Routing and Integration

For applications that use routes or APIs:

- [ ] Check that referenced pages and route handlers exist.
- [ ] Check navigation links and route parameters.
- [ ] Check API paths, HTTP methods, and response handling.
- [ ] Check authentication and authorization where relevant.
- [ ] Check loading, success, empty, and error states where applicable.

## 6. Security

- [ ] Check for exposed secrets and credentials.
- [ ] Review input validation and potentially unsafe operations.
- [ ] Review authentication and authorization changes.
- [ ] Run an appropriate dependency audit if available.
- [ ] Investigate security warnings instead of suppressing them.
- [ ] Never print or expose secrets during diagnosis or reporting.

## 7. Build and Release

- [ ] Run the relevant build command when appropriate.
- [ ] Check that required environment variables are documented.
- [ ] Review configuration and dependency changes.
- [ ] Run smoke tests when practical.
- [ ] Do not claim production readiness without sufficient verification.

## 8. Final Report

Ensure the final report includes:

- [ ] Changes summary.
- [ ] Checks discovered and planned.
- [ ] Checks executed and statuses (`PASS`, `FAIL`, `TIMEOUT`, `COMMAND_NOT_FOUND`, `NOT_RUN`, `UNCLASSIFIED`).
- [ ] Diagnosed failures with verbatim evidence and source locations.
- [ ] Files changed by the agent.
- [ ] Repair attempts used (out of 3) with rationales.
- [ ] Checks rerun and outcomes.
- [ ] Final verification status (`VERIFIED`, `PARTIALLY_VERIFIED`, `UNRESOLVED`).
- [ ] Remaining risks, uncertainties, and limitations.
- [ ] Safety notice explicitly stating passing checks do not prove zero defects.
- [ ] Recommended next step.

Never mark a check as passed unless it was actually executed and its result was inspected.

---

## 9. Production-Readiness Verification (Catalog-Grounded)

When performing release verification for production web applications, consult the **Production-Readiness Test Catalog** (`references/production-test-catalog.json`):

### Risk-Based Catalog Selection
- [ ] Inspect application architecture: routes, APIs, roles, data persistence, and existing tests.
- [ ] Map Critical User Journeys (CUJs) across onboarding, transactions, navigation, and recovery.
- [ ] Select applicable catalog cases based on explicit applicability rules.
- [ ] Do NOT test features the application does not have (e.g. OAuth, payments, multi-tenancy, background queues).
- [ ] Distinguish automation tiers: `automated_available`, `app_specific_automation`, and `manual_review`.

### Behavioral Verification & Journey Tracing
- [ ] Verify actual runtime behavior, not mere component, file, or route presence.
- [ ] Trace complete authentication lifecycles: credentials -> API response -> token storage -> redirect -> page load -> refresh -> logout -> protected route denial.
- [ ] Do not guess or hallucinate expected product behavior; mark ambiguous rules for clarification.

### Capacity Planning & Load Safety
- [ ] Treat 100,000 users as an architectural capacity model, not a universal test default.
- [ ] Distinguish registered users, daily visits, concurrent connections, and peak request rate (RPS).
- [ ] Never claim 100,000 user support based on a unit test, smoke test, or single-user run.
- [ ] Execute load or stress tests only in an explicitly approved, isolated staging environment with a defined workload. Never test live production or third-party APIs invasively.

### Explicit 7-State Accounting
- [ ] Classify every evaluated catalog case into: `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`, `NOT_APPLICABLE`, `MANUAL_REVIEW`, or `UNKNOWN`.
- [ ] Never treat a missing test, skipped check, or unavailable tool as a pass.

### Release Readiness Gating
- [ ] Pre-deployment: Run safe static checks, unit/integration suites, production build, and pre-deploy catalog cases.
- [ ] Post-deployment: Run only authorized, non-destructive smoke checks against the deployed URL.
- [ ] Emit a Production Readiness Assessment Report with an explicit release verdict: `READY`, `NOT_READY`, or `READY_WITH_ACCEPTED_RISKS`.
- [ ] Explicitly state safety limitations: verification verifies executed checks under test conditions, never guaranteeing zero defects.
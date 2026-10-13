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

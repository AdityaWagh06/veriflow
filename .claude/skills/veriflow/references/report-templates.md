# Veriflow Report Templates Reference

The two standardized report formats. Read the one that matches what you did:
the completion report after verifying a change, the readiness assessment after
a release review.

Both exist to separate what was actually executed from what was assumed. Never
fill in a status you did not observe.

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
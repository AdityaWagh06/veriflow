# Veriflow Production-Readiness Reference

The risk-based, catalog-driven workflow for assessing whether an application is
ready to deploy. Read this only when preparing a release or performing a
readiness review -- not for routine change verification.

Backed by `references/production-test-catalog.json` (145 cases, 15 categories)
and `references/production-test-catalog-guide.md`.

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

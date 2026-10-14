# Veriflow Production-Readiness Test Catalog Guide

This reference guide documents the structure, schema, category taxonomy, applicability rules, and automation statuses of the machine-readable test catalog located at [`production-test-catalog.json`](production-test-catalog.json).

---

## 1. Overview & Objective

AI coding agents often generate websites and applications that appear visually complete but suffer from hidden production defects:
- Fragile or incomplete authentication and session handling
- Broken route refreshes in single-page application (SPA) deployments
- Unhandled 4xx/5xx API responses and missing error boundaries
- Missing form validation or data loss during failed submissions
- Insecure direct object references (IDOR) and unauthorized privileged route access
- Layout overflows, unhandled promise rejections, and dead buttons
- Accessibility barriers for keyboard and screen reader users
- Security gaps (missing security headers, XSS, unescaped queries, exposed secrets)
- Unbounded list rendering, memory leaks, and unrealistic performance claims
- Fragile deployments missing environment variables or health checks

The **Production-Readiness Test Catalog** provides an authoritative, research-backed reference of **135 concrete test cases** across **15 categories** to help AI coding agents systematically verify web applications before and after deployment.

> [!NOTE]
> **Defect Reduction, Not Bug-Free Guarantees**: Passing verification checks confirms that executed assertions passed under specific test conditions; it does not promise zero bugs or guarantee that an application can handle arbitrary traffic loads.

---

## 2. Schema Specification

The catalog is stored as standard JSON (`production-test-catalog.json`). Each test case conforms to the following schema:

| Property | Type | Description |
|---|---|---|
| `id` | `string` | Unique, stable identifier with category prefix (e.g. `AUTH-001`, `ROUTE-002`, `SEC-005`). |
| `category` | `string` | Primary category ID matching one of the 15 standard categories. |
| `subcategory` | `string` | Granular functional area (e.g. `session_management`, `server_rewrites`, `idor_defense`). |
| `name` | `string` | Clear, concise title of the test case. |
| `defect_target` | `string` | Specific bug, vulnerability, or failure mode the test is designed to uncover. |
| `applicability_rules` | `object` | Explicit conditions required for the test to be applicable (e.g. `requires_authentication: true`). |
| `severity` | `string` | Risk level: `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW`. |
| `preconditions` | `array<string>` | State, environment setup, and test data required before running the test. |
| `steps` | `array<string>` | Deterministic, step-by-step reproduction instructions. |
| `expected_result` | `string` | Verifiable expected outcome matching documented product design. |
| `recommended_automation_method` | `string` | Preferred testing tool (e.g. `playwright_e2e`, `pytest_api`, `axe_core_audit`, `static_config_check`, `curl_smoke_check`, `lighthouse_cli`). |
| `automation_status` | `string` | Automation tier: `automated_available`, `app_specific_automation`, or `manual_review`. |
| `evidence_required` | `array<string>` | Concrete artifacts to collect (e.g. screenshots, HTTP status, DOM attributes, server logs). |
| `execution_phase` | `string` | When to run: `pre_deployment`, `post_deployment`, or `both`. |
| `safety_constraints` | `string` | Constraints preventing destructive operations, live data pollution, or unauthorized scanning. |
| `citations` | `array<string>` | Technical references grounding the test in established industry standards. |

---

## 3. The 15 Test Categories

| Prefix | Category Name | Test Count | Focus Area |
|:---:|---|:---:|---|
| `AUTH` | **Authentication and Account Flows** | 15 | Login, registration, password reset, session persistence, token expiry, multi-tab sync, duplicate prevention. |
| `ROUTE` | **Routing and Navigation** | 9 | Direct URL loading, SPA refresh rewrites, history traversal, 404 handling, route guards, mobile navigation. |
| `FORM` | **Forms and Input Handling** | 9 | Required fields, boundary validation, whitespace trimming, Enter-key submission, click debouncing, server parity. |
| `DATA` | **Core Business Logic and Data Integrity** | 9 | CRUD cycles, arithmetic/financial precision, zero states, pagination, optimistic UI rollbacks, tenant isolation. |
| `ROLE` | **User Roles and Authorization** | 8 | Public vs private boundaries, API authorization, IDOR defense, dynamic privilege revocation, multi-tenancy. |
| `API` | **API and Integration Reliability** | 9 | Schema validation, 4xx/5xx handling, timeouts, offline detection, rate limiting, missing environment variables. |
| `UIUX` | **UI Quality and User Experience** | 9 | Dead button detection, view states (loading/empty/error), horizontal overflow, modal focus trapping, console errors. |
| `A11Y` | **Accessibility** | 9 | Keyboard navigation, focus rings, heading hierarchy, accessible names, label binding, WCAG AA contrast, reduced motion. |
| `SEC` | **Security (OWASP Grounded)** | 11 | XSS reflection defense, SQL/NoSQL injection, CSRF protection, open redirects, secret scanning, cookie flags, security headers. |
| `PERF` | **Performance and Scalability** | 9 | Core Web Vitals (LCP/CLS/INP), bundle budgets, N+1 query detection, list virtualization, memory leaks, 100k capacity modeling. |
| `RESL` | **Resilience and Reliability** | 8 | DB reconnection, backend outage fallbacks, circuit breakers, exponential backoff, graceful shutdown, health probes. |
| `CONF` | **Deployment and Production Configuration** | 8 | Production build verification, env variable audit, secret exclusion, HTTPS/HSTS, migration safety, smoke checklists. |
| `SEO` | **Search, Metadata, and Discoverability** | 7 | Meta tags, canonical links, robots/sitemap, private route noindex, social OpenGraph tags, structured data, semantic 404s. |
| `NETW` | **Browser Compatibility and Network Behavior** | 7 | Cross-browser engines (Chromium/Firefox/WebKit), CORS validation, mixed content, third-party script resilience. |
| `OBSV` | **Observability and Post-Deployment Verification** | 8 | Structured JSON logging, correlation IDs, error telemetry, Four Golden Signals metrics, post-deploy smoke, rollback triggers. |

---

## 4. Standardized Result States

When verifying an application against catalog cases, agents must classify each check into one of the following explicit states:

- **`PASS`**: The check was explicitly executed and passed all verification criteria with supporting evidence.
- **`FAIL`**: The check was explicitly executed and failed (asserted outcome was not met, exit code was non-zero, or error diagnostic was produced).
- **`BLOCKED`**: The check could not execute because an essential prerequisite, credential, external dependency, or environment permission was unavailable.
- **`NOT_RUN`**: The check is applicable to the application, but was not executed during this verification session.
- **`NOT_APPLICABLE`**: The check does not apply to this application based on its documented architecture (e.g. an application without authentication skips `AUTH-*` with reason: `No authentication configured`).
- **`MANUAL_REVIEW`**: The check requires human judgment, design clarification, assistive technology evaluation, or operational disaster drills.
- **`UNKNOWN`**: Available evidence is inconclusive or ambiguous; cannot determine pass or fail without further investigation.

> [!CAUTION]
> **Prohibition on False Passing**: Never mark a check as `PASS` if it was skipped, blocked, unverified, or omitted due to missing tools. A missing test is `NOT_RUN` or `BLOCKED`, never `PASS`.

---

## 5. Automation Tiers: What Is Executable Today

The catalog distinguishes three tiers of automation readiness:

1. **`automated_available` (51 test cases)**:
   - Executable with general-purpose tools already available in modern development stacks:
     - Static checks (`py_compile`, linting, build checks, secret scanning, bundle inspection).
     - Standard HTTP/API probes (`curl_smoke_check`, `pytest_api` contract validations).
     - Automated DOM scans (`axe_core_audit` via CLI or test runner).
   - Can be run directly by Veriflow's verification runner or standard scripts.

2. **`app_specific_automation` (73 test cases)**:
   - Fully automatable in code, but requires application-specific test scripts, DOM selectors, seed data, and journey flows (e.g. custom Playwright E2E tests, seeded databases, or route mocks).
   - The coding agent can write and execute these tests using the project's existing test framework.

3. **`manual_review` (11 test cases)**:
   - High-level capacity planning, backup recovery drills, manual assistive tech reviews, or architectural sign-offs that require human authorization or external infrastructure.

---

## 6. How to Query and Use the Catalog in Veriflow

### Step 1: Discover Project Capabilities
Inspect the target application's project files, dependencies, routes, and documentation. Determine which capabilities exist:
- Does it have authentication? (`requires_authentication`)
- Does it have forms or file uploads? (`has_forms`, `supports_file_uploads`)
- Does it have multiple user roles? (`has_role_based_access_control`)
- Does it have a database or API? (`has_database`, `has_api`)

### Step 2: Filter Applicable Catalog Entries
Select only test cases whose `applicability_rules` match the detected application capabilities.
- Do NOT mandate payment, OAuth, multi-tenancy, or background workers if the application does not have them.
- If a business rule is unclear, mark the item as `MANUAL_REVIEW` or request clarification rather than inventing requirements.

### Step 3: Run Available Automated Checks
Run existing project test suites and static checks using Veriflow:
```bash
python skills/veriflow/scripts/run-checks.py [project-dir] --execute
```

### Step 4: Write App-Specific Tests for Critical User Journeys
For critical missing coverage (e.g. `AUTH-001`, `ROUTE-005`, `FORM-001`, `SEC-001`), implement targeted test cases in the project's test suite and verify using `--check`:
```bash
python skills/veriflow/scripts/run-checks.py [project-dir] --check test --execute
```

---

## 7. Adding New Test Cases to the Catalog

To add a new test case:
1. Ensure the ID follows the prefix convention (`<CATEGORY_PREFIX>-<NUMBER>`, e.g. `AUTH-016`).
2. Provide all 16 required schema fields.
3. Validate uniqueness against existing catalog IDs.
4. Verify JSON syntax and run the automated catalog test suite:
   ```bash
   pytest tests/test_production_test_catalog.py -v
   ```

---

## 8. Grounding References & Citations

The catalog is grounded in the following technical standards:
1. **OWASP Authentication Cheat Sheet**: [https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
2. **OWASP Session Management Cheat Sheet**: [https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
3. **OWASP Authorization Cheat Sheet**: [https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
4. **OWASP Web Security Testing Guide (WSTG)**: [https://owasp.org/www-project-web-security-testing-guide/](https://owasp.org/www-project-web-security-testing-guide/)
5. **Playwright Authentication Documentation**: [https://playwright.dev/docs/auth](https://playwright.dev/docs/auth)
6. **Playwright Network Testing Guide**: [https://playwright.dev/docs/network](https://playwright.dev/docs/network)
7. **Google web.dev Core Web Vitals**: [https://web.dev/articles/vitals](https://web.dev/articles/vitals)
8. **Google SRE Launch Checklist**: [https://sre.google/sre-book/launch-checklist/](https://sre.google/sre-book/launch-checklist/)

---

## 9. Browser and User-Journey Automation Mapping (Phase 2)

Phase 2 introduces automated client-side browser testing for critical catalog journeys via Playwright.

### Mapping Index (`browser-test-mapping.json`)
The mapping between catalog test cases and executable browser automation is stored in [`browser-test-mapping.json`](browser-test-mapping.json). Each entry defines:
- `catalog_id`: The matching catalog test ID (e.g. `AUTH-001`, `ROUTE-001`).
- `name`: Descriptive test name.
- `journey_function`: The python automation routine in `browser_journeys.py`.
- `category`: The functional category (`AUTH`, `ROUTE`, `ROLE`, `FORM`, `UIUX`).
- `required_elements`: Key DOM selectors expected by the journey (e.g. `#username`, `#password`, `#submit-login`).

### Currently Executable Browser Journeys
17 production catalog cases are currently automated and verified against the deterministic demo fixture and real web targets:
- **Authentication**: `AUTH-001` (valid login), `AUTH-002` (invalid login), `AUTH-003` (missing account recovery link), `AUTH-005` (duplicate registration), `AUTH-006` (password visibility toggle), `AUTH-007` (logout session invalidation), `AUTH-008` (session persistence across reload).
- **Access Control**: `ROLE-002` (unauthenticated protected route rejection).
- **Routing & Navigation**: `ROUTE-001` (primary navbar links), `ROUTE-003` (history back/forward traversal), `ROUTE-004` (unknown route 404 recovery).
- **Forms & Validation**: `FORM-001` (required field validation), `FORM-003` (boundary input handling), `FORM-005` (keyboard Enter submission).
- **User Experience & Telemetry**: `UIUX-004` (mobile viewport reflow & overflow check), `UIUX-007` (browser console error collection), `UIUX-008` (failed network request collection).

### Execution via Veriflow
- **Via Standard Check Runner**:
  ```bash
  python skills/veriflow/scripts/run-checks.py . --check browser --execute
  ```
- **Via Standalone Browser Runner**:
  ```bash
  python skills/veriflow/scripts/run-browser-tests.py --url http://localhost:3000 --execute
  ```
- **Demo Runner with Fault Injection**:
  ```bash
  python examples/browser-demo/run-demo.py --fault broken_login
  ```

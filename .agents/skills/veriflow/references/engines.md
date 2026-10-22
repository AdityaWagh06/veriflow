# Veriflow Verification Engines Reference

The four opt-in verification engines, their automated coverage, their safety
boundaries, and their exact commands. Read the section for the engine a change
actually touches; do not read all four.

| Engine | Read this when the change touches | Prerequisite |
| :--- | :--- | :--- |
| API & Integration | HTTP handlers, routes, status codes, error payloads | a running local service |
| OpenAPI Contract | a published OpenAPI/Swagger specification | a spec file; PyYAML for YAML |
| Browser & User Journey | pages, forms, routing, sessions, layout | Playwright (optional) |
| Security | anything (static half needs nothing at all) | none for static; a local service for live |

---

### 6. Check Integrations and Routing (API & Integration Verification Engine)

When verifying APIs, backend endpoints, and integrated microservices, invoke the Phase 3 **API & Integration Verification Engine** to validate real HTTP behavior without making blind assumptions.

#### Automated API Verification Capabilities
Veriflow supports a practical, bounded set of standard library-based checks:
1. **Health and Readiness Probes**: Verifies `/health` and `/ready` return HTTP 200 with JSON status payload (`RESL-006`, `API-READY`).
2. **Response Schema Contracts**: Validates HTTP 200, Content-Type headers, required JSON fields, data types, and non-empty responses (`API-001`).
3. **Client Input Validation**: Proves missing required fields or invalid numeric inputs produce HTTP 400 Bad Request with actionable client error payloads (`FORM-001`, `API-002`).
4. **Authentication Gate Enforcement**: Verifies unauthenticated requests to protected endpoints receive HTTP 401 Unauthorized without session leaks (`AUTH-001`).
5. **Role-Based Authorization Denial**: Validates standard authenticated user tokens are denied access (`403 Forbidden`) to administrative or privileged endpoints (`ROLE-003`).
6. **Server Error Defense & Traceback Suppression**: Triggers intentional failure endpoints to ensure HTTP 500 responses return generic JSON errors without leaking raw language tracebacks, file paths, database credentials, or secret keys (`SEC-009`, `API-003`).
7. **Defensive Parsing**: Validates API clients and handlers handle malformed JSON and unexpected MIME types gracefully without crashing (`API-004`).
8. **Request Timeouts & Network Delays**: Enforces bounded per-request timeouts (default 5.0s) and verifies timeouts fail fast with structured failure diagnostics (`RESL-007`).
9. **Integration & Outage Degradation**: Tests downstream dependency status endpoints (`/api/dependency/status`) for structured HTTP 503 fallback metadata during external service outages (`API-008`).
10. **Rate Limiting Compliance**: Validates HTTP 429 Too Many Requests status and Retry-After response headers under high-frequency request bursts (`API-007`).
11. **CRUD Lifecycle & Data Consistency**: Tests sequential creation, retrieval, and state consistency across related API endpoints (`DATA-004`).
12. **HTTP Method & Routing Boundaries**: Tests unsupported verbs (e.g. `PATCH`, `DELETE`) on read-only endpoints return HTTP 405 Method Not Allowed or 404 Not Found (`API-005`).

#### Safety Boundaries & Policies
- **Strict Local Loopback by Default**: Targets must be on `127.0.0.1`, `localhost`, or `::1`. Remote and production URLs are blocked unless explicit local resolution is verified.
- **Preview by Default**: Running without `--execute` previews planned checks without sending any HTTP requests.
- **Credential Redaction**: Authorization headers (`Bearer [REDACTED]`), Cookie headers, passwords, and tokens are stripped from reports.
- **Zero Third-Party Dependencies**: Built entirely with Python's standard library (`urllib.request`, `http.server`, `json`).
- **Bounded Response Capture**: Body snippets are capped (default 16 KB) to prevent report bloat.

#### Running API Verification
```bash
# Preview API checks via unified runner
python <path-to-skill>/scripts/run-checks.py . --check api

# Execute API checks via unified runner
python <path-to-skill>/scripts/run-checks.py . --check api --execute

# Standalone runner preview
python <path-to-skill>/scripts/run-api-tests.py

# Standalone runner execution against local fixture
python <path-to-skill>/scripts/run-api-tests.py --execute

# Execute against an existing local service
python <path-to-skill>/scripts/run-api-tests.py --execute --url http://127.0.0.1:8000

# JSON formatted report
python <path-to-skill>/scripts/run-api-tests.py --execute --json
```

### Phase 4: OpenAPI Contract Verification Engine

When verifying APIs against published OpenAPI contracts, invoke the Phase 4 **OpenAPI Contract Verification Engine** to validate that live API implementations adhere strictly to their documented specifications without schema drift.

#### Automated OpenAPI Verification Capabilities
Veriflow supports contract-driven testing for OpenAPI 3.0 and 3.1 specifications in JSON and YAML formats:
1. **Static Specification Validation**: Verifies document structure, required top-level fields (`openapi`, `info`, `paths`), and supported versions without sending live network requests (`CONF-004`).
2. **Safe Reference Resolution**: Resolves internal JSON Pointer `$ref` references safely, detects circular references without infinite recursion, and blocks path traversal attempts (`../`) and arbitrary remote HTTP `$ref` URLs (`CONF-004`).
3. **Response Schema Contract Compliance**: Validates that live endpoints return documented status codes, expected `Content-Type` media types (e.g. `application/json`), required properties, correct data types (string, integer, number, boolean, array, object), enums, and numerical min/max boundaries (`API-001`, `RESL-006`).
4. **Authentication Gate Enforcement**: Verifies operations with declared `security` requirements enforce authentication boundaries, returning HTTP 401 Unauthorized when tokens are omitted (`AUTH-001`).
5. **Input Validation Boundaries**: Proves invalid inputs or missing required parameters produce HTTP 400 Bad Request responses rather than unhandled server errors (`API-002`).
6. **Graceful YAML Dependency Handling**: Supports YAML specifications when PyYAML is installed. If PyYAML is missing, Veriflow reports a `BLOCKED` status with explicit installation instructions rather than crashing or silently skipping.
7. **Strict Separation of Validation & Live Execution**: Allows specification validation independently of endpoint availability. An API can be offline while its spec is valid, or live while violating its contract.

#### Safety Boundaries & Policies
- **Strict Local Loopback by Default**: Targets must be on `127.0.0.1`, `localhost`, or `::1`. External URLs require explicit `--allow-external` authorization with a safety warning.
- **Preview by Default**: Running without `--execute` displays planned contract checks without dispatching live HTTP calls.
- **Zero Third-Party Dependencies for JSON**: Built on Python's standard library (`urllib.request`, `http.server`, `json`).
- **Credential & Token Redaction**: Authorization headers, Bearer tokens, passwords, and sensitive keys are masked in console diagnostics and JSON reports.
- **Bounded Response Capture**: Body snippets in failure diagnostics are strictly capped to prevent report bloat.
- **Non-Destructive by Default**: Potentially state-altering operations (e.g. `DELETE`) are flagged for `MANUAL_REVIEW` under default verification rules.

#### Running OpenAPI Verification
```bash
# Preview OpenAPI checks via unified runner
python <path-to-skill>/scripts/run-checks.py . --check openapi

# Execute OpenAPI checks via unified runner
python <path-to-skill>/scripts/run-checks.py . --check openapi --execute

# Standalone runner preview
python <path-to-skill>/scripts/run-openapi-tests.py --spec path/to/openapi.json

# Static specification validation only (zero HTTP requests)
python <path-to-skill>/scripts/run-openapi-tests.py --spec path/to/openapi.json --validate-spec-only

# Standalone execution against running service
python <path-to-skill>/scripts/run-openapi-tests.py --spec path/to/openapi.json --url http://127.0.0.1:8000 --execute

# Targeted operation filtering
python <path-to-skill>/scripts/run-openapi-tests.py --spec path/to/openapi.json --url http://127.0.0.1:8000 --execute --check getHealth

# JSON formatted report
python <path-to-skill>/scripts/run-openapi-tests.py --spec path/to/openapi.json --url http://127.0.0.1:8000 --execute --json
```

---

### 8. Browser and User-Journey Verification Engine (Phase 2)

AI coding agents commonly produce web applications that appear complete or pass unit tests, but fail in production on real user journeys. Veriflow integrates an incremental, opt-in **Browser and User-Journey Automation Engine** powered by Playwright to test real browser behavior.

#### Why Browser Testing is Essential
- **Beyond Shallow Code Inspection**: Verifies that buttons actually trigger actions, routes properly guard protected resources, forms render server validation errors, and sessions persist across page refreshes.
- **Client-Side Telemetry**: Collects unhandled client-side JavaScript console errors and failed background network requests (4xx/5xx).
- **Responsive Layout Verification**: Tests desktop and mobile viewports (`375x667`) to detect horizontal scroll overflow and layout breaks.

#### Safety & Dependency Rules
1. **Playwright is Strictly Optional**: Browser testing is not a hard dependency for Veriflow. If Playwright or browser binaries are missing, Veriflow reports `BLOCKED` with clear remediation commands rather than failing or crashing.
2. **Zero Automatic Installations**: Veriflow will never execute `pip install` or download browser binaries automatically.
3. **Preview-Only by Default**: Like all Veriflow checks, browser checks run in preview mode by default. Explicit `--execute` authorization is required to launch browser processes.
4. **Credential & Secret Redaction**: Passwords, session cookies, authorization headers, and bearer tokens are automatically masked (`[REDACTED]`) from logs, diagnostics, and reports.
5. **No Destructive External Testing**: Browser tests execute only against local fixtures or explicitly authorized staging URLs. Never run destructive actions against production systems.

#### The 15 Core User Journeys
The engine provides reusable test templates for the most critical user journeys:
1. **Valid Login Journey** (`AUTH-001`): Form accepts valid credentials and renders post-login welcome UI.
2. **Invalid Login Handling** (`AUTH-002`): Invalid credentials produce clear, actionable error feedback.
3. **Nonexistent Account Handling** (`AUTH-003`): Unrecognized account prompt offers registration or recovery.
4. **Post-Authentication Redirection**: Authenticated user is navigated to originally requested destination.
5. **Duplicate Registration Validation** (`AUTH-005`): Validates required fields and catches duplicate username/email conflicts.
6. **Protected Route Guard Enforcement** (`ROLE-002`): Unauthenticated requests to protected pages are rejected.
7. **Logout Session Invalidation** (`AUTH-007`): Logout invalidates session tokens; back-navigation is rejected.
8. **Session Persistence Across Reload** (`AUTH-008`): Authenticated session survives full browser page refresh.
9. **History Traversal** (`ROUTE-003`): Browser back and forward buttons navigate history without breaking state.
10. **404 Route Recovery** (`ROUTE-004`): Unknown routes render a helpful 404 page with recovery navigation.
11. **Form Input Retention**: Forms retain valid input fields after recoverable validation errors.
12. **Primary Navigation Links** (`ROUTE-001`): Navbar links navigate to valid destinations without broken links.
13. **Browser Console Error Telemetry** (`UIUX-007`): Intercepts unhandled console errors and runtime exceptions.
14. **Failed Network Request Telemetry** (`UIUX-008`): Intercepts failed AJAX/fetch calls and HTTP 5xx responses.
15. **Responsive Viewport Reflow** (`UIUX-004`): Mobile viewport check detects horizontal page overflow.

#### Deterministic Local Demo & Fault Injection
Veriflow includes a self-contained local web application fixture (`skills/veriflow/demo_app/server.py`) that runs on an ephemeral port. It features built-in fault injection modes:
- `fault_broken_login`: Simulates incorrect post-login redirection.
- `fault_open_protected_route`: Simulates a broken route guard allowing unauthenticated access.
- `fault_missing_validation`: Simulates server-side form validation silence.
- `fault_broken_link`: Simulates broken internal navigation links.
- `fault_console_error`: Simulates unhandled JavaScript runtime exceptions.
- `fault_server_500`: Simulates server-side 500 internal errors on API requests.

Veriflow verifies that browser tests genuinely fail on broken fixtures and pass on corrected fixtures.

#### Integration into the 9-Step Bounded Repair Workflow
When a browser journey fails during verification:
1. Veriflow captures structured browser diagnostics: current URL, page title, failed selector or assertion, console logs, and network failures.
2. The agent analyzes the captured diagnostic evidence in Step 5.
3. The agent proposes or applies a minimal fix in Step 6 (within the 3-attempt budget).
4. The agent re-runs only the failing browser journey or category via `--check browser --execute` or `run-browser-tests.py --filter <id> --execute` in Step 7.
5. Once resolved, broader verification runs in Step 8 to ensure zero regressions.

---

# Veriflow Browser & User-Journey Verification Demo

This example demonstrates Veriflow's Phase 2 **Browser & User-Journey Verification Engine**.

AI coding agents frequently produce web applications that look visually finished or pass basic unit tests, but fail in production on real user journeys: broken login redirections, bypassable route guards, unhandled form errors, unhandled JavaScript exceptions, or broken mobile viewport layouts.

Veriflow provides deterministic, sandboxed browser verification powered by Playwright to catch these issues before deployment.

---

## Key Safety & Architecture Principles

1. **Browser Testing is Optional**: Veriflow never requires Playwright as a hard dependency. If Playwright or browser binaries are not installed, Veriflow gracefully reports `BLOCKED` with specific remediation steps instead of crashing.
2. **No Automatic Package Installation**: Veriflow will never execute `pip install` or `playwright install` behind your back.
3. **Preview-Only by Default**: Like all Veriflow checks, browser verification runs in preview mode by default. Live browser launch requires explicit authorization (`--execute`).
4. **Credential & Secret Redaction**: Passwords, session cookies, auth headers, and bearer tokens are automatically masked (`[REDACTED]`) from diagnostic summaries and JSON reports.
5. **No Destructive External Testing**: Browser verification targets only explicitly authorized URLs or local fixtures.

---

## 1. Checking Browser Automation Availability

You can inspect your browser automation environment at any time using:

```bash
python skills/veriflow/scripts/run-checks.py . --check browser
```

Or via the standalone runner:

```bash
python skills/veriflow/scripts/run-browser-tests.py
```

The output shows:
- Whether the `playwright` Python library is importable.
- Detected system browser channels (e.g., `chrome`, `msedge`, or bundled `chromium`).
- Browser status: `AVAILABLE` or `BLOCKED`.
- Actionable remediation if `BLOCKED` (e.g. `pip install playwright`).

---

## 2. Running the Browser Demo

### A. Preview Mode (Safe, No Execution)
Preview the planned journey checks and required DOM selectors without launching a browser:

```bash
python examples/browser-demo/run-demo.py --preview
```

### B. Clean Baseline Execution
Launches the built-in deterministic demo web application on an ephemeral port, executes all 17 mapped user-journey tests, collects diagnostic telemetry, shuts down the server, and prints results:

```bash
python examples/browser-demo/run-demo.py
```

All journeys pass (`PASS: 17, FAIL: 0`).

### C. Category Filtering
Run only a specific subset of journeys (e.g. authentication):

```bash
python examples/browser-demo/run-demo.py --filter auth
```

Supported filters: `AUTH`, `ROUTE`, `ROLE`, `FORM`, `UIUX`, or specific test IDs like `AUTH-001`.

---

## 3. Testing Fault Detection (Proving Tests Truly Fail)

A verification suite is only trustworthy if it actively catches real bugs. The demo application includes deterministic fault injection switches to simulate common coding agent errors:

| Fault Flag | Injected Defect | Detected By | Expected Result |
| :--- | :--- | :--- | :--- |
| `--fault broken_login` | Login button navigates to `/dashboard` even when credentials are invalid | `AUTH-002` | **FAIL** (error message missing) |
| `--fault open_protected_route` | `/profile` page rendered without checking session cookie | `ROLE-002` | **FAIL** (unauthorized access permitted) |
| `--fault missing_validation` | Server registration fails without returning feedback to form | `AUTH-005`, `FORM-001` | **FAIL** (validation banner missing) |
| `--fault broken_link` | Primary navbar link points to broken route `/broken-link` | `ROUTE-001` | **FAIL** (navigation failure detected) |
| `--fault console_error` | Page triggers `TypeError: Cannot read properties of undefined` | `UIUX-007` | **FAIL** (unhandled console error captured) |
| `--fault server_500` | Profile API returns HTTP 500 Internal Server Error | `UIUX-008` | **FAIL** (failed network request captured) |

Try running a fault simulation:

```bash
python examples/browser-demo/run-demo.py --fault broken_login
```

Veriflow will report:
- `AUTH-002: FAIL`
- Captured current URL, page title, and failure assertion.
- Redacted diagnostic context.
- Exit code 1 indicating failure.

---

## 4. Adapting Browser Verification to Your Application

To adapt Veriflow's browser journeys to your own application:

1. **Verify Your Application URL**:
   Ensure your local dev server is running (e.g., `http://localhost:3000`).

2. **Execute Against Your Target**:
   ```bash
   python skills/veriflow/scripts/run-browser-tests.py --url http://localhost:3000 --execute
   ```

3. **Custom Selector & Route Configuration**:
   The catalog mappings (`skills/veriflow/references/browser-test-mapping.json`) define default selector expectations:
   - Login form: `#username`, `#password`, `#submit-login`
   - Registration: `#reg-username`, `#reg-email`, `#reg-password`, `#submit-register`
   - Protected route: `/profile` (or any route requiring active session)
   - Navigation: Primary nav anchors or buttons.

   If your app uses different IDs (e.g., `input[name="email"]`), customize or map selectors in `skills/veriflow/scripts/browser_journeys.py`.

---

## 5. Automated vs. Manual Catalog Checks

Veriflow's Production Test Catalog contains 135 total verification cases across 12 categories:
- **Automated in Phase 2**: Core functional user journeys (authentication, route guards, session persistence across reload, client form validation, history traversal, console error telemetry, network failure telemetry, and mobile viewport overflow).
- **Manual / Staged for Later Phases**: Complex OAuth multi-factor providers, real payment gateway webhooks, volumetric DDoS resilience, and deep screen-reader accessibility auditing.

Blocked tests (`BLOCKED`) indicate missing tooling or unmet prerequisites, distinctly separated from failing tests (`FAIL`), which indicate defective application code.

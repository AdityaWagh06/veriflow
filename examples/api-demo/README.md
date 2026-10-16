# Veriflow API & Integration Verification Demo

This example demonstrates Veriflow's Phase 3 **API & Integration Verification Engine**.

AI coding agents frequently produce backend services and REST APIs that appear functionally complete or pass shallow mock tests, but fail in real environments: subtle JSON schema changes that break client contracts, unhandled client inputs, raw database stack traces leaked on 500 errors, authentication and authorization bypasses, unhandled timeouts, or unhandled third-party dependency outages.

Veriflow provides a safe, deterministic, zero-dependency API verification layer built entirely on Python's standard library (`urllib.request`, `http.server`, `json`).

---

## Key Safety & Architecture Principles

1. **Zero External Dependencies**: The API verification engine requires only Python 3.8+ standard library modules. No third-party HTTP clients or frameworks are required.
2. **Loopback-Only by Default**: To prevent accidental testing or denial-of-service against production or third-party targets, Veriflow restricts execution to local loopback interfaces (`127.0.0.1`, `localhost`, `::1`) by default.
3. **Preview-Only by Default**: In `run-checks.py` and `run-api-tests.py`, checks run in discovery preview mode unless explicitly executed with `--execute`.
4. **Credential & Secret Redaction**: Request headers (e.g. `Authorization: Bearer [REDACTED]`, `Cookie: [REDACTED]`) and sensitive body parameters (passwords, tokens, API keys) are masked automatically in console and JSON reports.
5. **Bounded Response Capture**: Diagnostic snippets and bodies are strictly capped to prevent memory exhaustion or report bloat from massive responses.
6. **No Destructive Operations**: Tests use disposable test items and non-destructive HTTP methods.

---

## 1. Running the API Verification Demo

### A. Preview Mode (Safe, Zero HTTP Requests)
Preview planned API checks without starting any server or sending any network traffic:

```bash
python examples/api-demo/run-demo.py --preview
```

### B. Clean Baseline Execution
Launches the built-in deterministic demo server on an ephemeral loopback port, runs all mapped API checks, validates results, shuts down the fixture, and reports findings:

```bash
python examples/api-demo/run-demo.py
```

All checks pass (`PASS: 12, FAIL: 0`).

### C. Filtering Checks
Run only a specific check or catalog test:

```bash
# Filter by catalog ID
python examples/api-demo/run-demo.py --filter API-001

# Filter by keyword (e.g. auth, schema, health)
python examples/api-demo/run-demo.py --filter auth
```

### D. Machine-Readable JSON Output
Emit structured JSON reports suitable for CI/CD pipelines or AI agent consumption:

```bash
python examples/api-demo/run-demo.py --json
```

---

## 2. Testing Fault Detection (Proving Real Defects are Caught)

A verification tool is only effective if it reliably detects defects. The demo application features deterministic fault injection modes simulating common backend regressions:

| Fault Flag | Injected Defect | Detected By | Expected Result |
| :--- | :--- | :--- | :--- |
| `--fault schema` | Drops required `price` field from item schema | `API-001` | **FAIL** (missing required schema fields: `['price']`) |
| `--fault stacktrace` | Leaks raw Python traceback and database credentials on crash | `SEC-009` | **FAIL** (leaks internal debug trace or secrets) |
| `--fault auth_bypass` | Permits unauthenticated access to `/api/profile` | `AUTH-001` | **FAIL** (expected HTTP 401, got HTTP 200) |
| `--fault role_bypass` | Permits non-admin user to read `/api/admin/metrics` | `ROLE-003` | **FAIL** (expected HTTP 403, got HTTP 200) |
| `--fault missing_validation` | Accepts negative item price without validation | `FORM-001` | **FAIL** (expected HTTP 400 for invalid inputs, got HTTP 201) |
| `--fault dependency` | Simulates third-party integration outage with 503 fallback | `API-008` | **PASS / DIAGNOSTIC** (graceful fallback validation) |

Try running a fault simulation:

```bash
python examples/api-demo/run-demo.py --fault schema
```

Veriflow will output:
- `API-001: FAIL`
- Exact missing schema fields (`price`)
- Response status code and duration
- Exit code 1 indicating failure

---

## 3. Integration with Veriflow Runner

You can also discover and run API verification via Veriflow's unified check runner:

```bash
# Preview API checks in the current project
python skills/veriflow/scripts/run-checks.py . --check api

# Execute API verification
python skills/veriflow/scripts/run-checks.py . --check api --execute
```

Or run the standalone API test runner directly:

```bash
# Preview
python skills/veriflow/scripts/run-api-tests.py

# Execute against local fixture
python skills/veriflow/scripts/run-api-tests.py --execute
```

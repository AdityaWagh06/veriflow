# Veriflow OpenAPI Contract Verification Demo

This example demonstrates Veriflow's Phase 4 **OpenAPI Contract Verification Engine**.

AI coding agents frequently update backend routes, controllers, and schemas without keeping OpenAPI specifications and live implementations aligned. Common defects include:
- Renaming or omitting documented response fields.
- Changing property data types (e.g. returning strings instead of booleans or numbers).
- Returning undocumented HTTP status codes.
- Emitting wrong content types (e.g. returning `text/html` error pages on JSON endpoints).
- Accepting invalid request bodies without validation or crashing with unhandled 500 errors.
- Committing invalid OpenAPI documents with syntax errors, broken `$ref` pointers, or unsupported versions.

Veriflow provides a safe, deterministic, contract-driven OpenAPI verification layer supporting OpenAPI 3.0 and 3.1 in JSON and YAML formats.

---

## Safety & Architecture Principles

1. **Zero External Dependencies for JSON**: JSON OpenAPI verification runs entirely on Python 3.8+ standard library modules (`urllib.request`, `http.server`, `json`).
2. **Graceful YAML Handling**: Optional PyYAML is utilized if present. If PyYAML is missing when loading YAML, Veriflow reports `BLOCKED` with actionable remediation guidance instead of crashing.
3. **Loopback-Only by Default**: Target URLs are strictly restricted to local loopback addresses (`127.0.0.1`, `localhost`, `::1`). External targets require explicit `--allow-external` authorization with safety warnings.
4. **Preview-Only by Default**: No live network requests are sent unless `--execute` is explicitly specified.
5. **Path Traversal & Remote `$ref` Protections**: Directory-escaping references (`../`) and arbitrary remote HTTP `$ref` URLs are rejected to prevent file disclosure or SSRF attacks. Circular references are safely tracked without infinite recursion.
6. **Credential Redaction**: Authorization tokens and secrets are redacted automatically in console and JSON reports.

---

## 1. Running the OpenAPI Demo

### A. Preview Mode (Safe, Zero HTTP Requests)
Preview planned contract checks without launching any server or making live HTTP calls:

```powershell
python examples/openapi-demo/run-demo.py --preview
```

### B. Specification Validation Only (Zero Network Traffic)
Validate specification syntax, required OpenAPI fields, and internal reference resolution without live execution:

```powershell
# Validate JSON specification
python examples/openapi-demo/run-demo.py --validate-spec-only

# Validate YAML specification
python examples/openapi-demo/run-demo.py --yaml --validate-spec-only
```

### C. Clean Baseline Execution
Launches the deterministic local demo fixture on an ephemeral loopback port, executes all generated contract checks against the specification, shuts down the fixture, and reports results:

```powershell
# Run against OpenAPI 3.0 JSON specification
python examples/openapi-demo/run-demo.py

# Run against OpenAPI 3.0 YAML specification
python examples/openapi-demo/run-demo.py --yaml
```

All contract checks pass cleanly:
```
============================================================
OpenAPI Contract Verification Report
============================================================
Total Checks: 8
Passed:       8
Failed:       0
Blocked:      0
Duration:     0.05s

Summary: PASS (100.0% passing)
============================================================
```

### D. Targeted Check Filtering
Filter execution by operationId or check type:

```powershell
# Run only health endpoint checks
python examples/openapi-demo/run-demo.py --check getHealth

# Run only profile endpoint checks
python examples/openapi-demo/run-demo.py --check getUserProfile
```

### E. Machine-Readable JSON Output
Output structured JSON reports for CI/CD or agent consumption:

```powershell
python examples/openapi-demo/run-demo.py --format json
```

---

## 2. Testing Fault Detection (Proving Contract Violations are Caught)

A contract verification engine must reliably catch genuine violations. The demo server includes targeted fault injection modes:

| Fault Flag | Injected Defect | Detected Check | Diagnostic Result |
| :--- | :--- | :--- | :--- |
| `--fault missing_field` | Omits required `price` field from `/api/items` response | `CONTRACT_listItems` | **FAIL**: Missing required property 'price' at root[0] |
| `--fault wrong_status` | Returns undocumented 500 status on `/api/health` | `CONTRACT_getHealth` | **FAIL**: Unexpected response status code 500 (documented: [200]) |
| `--fault wrong_content_type` | Returns `text/plain` instead of `application/json` | `CONTRACT_getHealth` | **FAIL**: Unexpected Content-Type 'text/plain' (documented: ['application/json']) |
| `--fault invalid_type` | Returns string `"yes"` for boolean `active` on `/api/profile` | `CONTRACT_getUserProfile` | **FAIL**: Expected boolean at root.active, got str ('yes') |
| `--fault request_validation` | Unhandled crash on invalid POST `/api/items` | `REQ_VAL_createItem` | **FAIL**: Unexpected response status code 500 (documented: [201, 400]) |

### Try Running Fault Scenarios:

```powershell
# 1. Missing required response property
python examples/openapi-demo/run-demo.py --fault missing_field

# 2. Undocumented status code
python examples/openapi-demo/run-demo.py --fault wrong_status

# 3. Content type mismatch
python examples/openapi-demo/run-demo.py --fault wrong_content_type

# 4. Property data type violation
python examples/openapi-demo/run-demo.py --fault invalid_type
```

Each fault mode halts with exit code 1 and outputs exact, actionable error diagnostics pinpointing the schema path and observed violation.

---

## 3. Testing Deliberately Broken Specifications

The demo includes isolated invalid specifications in `examples/openapi-demo/specs/` to demonstrate static validation enforcement:

```powershell
# 1. Unsupported OpenAPI version (Swagger 2.0 rejected)
python skills/veriflow/scripts/run-openapi-tests.py --spec examples/openapi-demo/specs/invalid_version.json --validate-spec-only

# 2. Malformed JSON syntax
python skills/veriflow/scripts/run-openapi-tests.py --spec examples/openapi-demo/specs/malformed_syntax.json --validate-spec-only

# 3. Missing required top-level fields (info, paths)
python skills/veriflow/scripts/run-openapi-tests.py --spec examples/openapi-demo/specs/missing_fields.json --validate-spec-only

# 4. Unresolved local $ref pointer
python skills/veriflow/scripts/run-openapi-tests.py --spec examples/openapi-demo/specs/unresolved_ref.json --validate-spec-only

# 5. Illegal directory-escaping path traversal $ref
python skills/veriflow/scripts/run-openapi-tests.py --spec examples/openapi-demo/specs/path_traversal_ref.json --validate-spec-only
```

Each test safely halts without crashes, returning informative error messages and exit code 1.

---

## 4. Standalone CLI & Unified Runner Usage

Run OpenAPI verification directly via the standalone runner:

```powershell
# Preview checks against a custom spec
python skills/veriflow/scripts/run-openapi-tests.py --spec path/to/openapi.json

# Execute against a running local service
python skills/veriflow/scripts/run-openapi-tests.py --spec path/to/openapi.json --url http://127.0.0.1:8000 --execute
```

Or discover and run OpenAPI checks via Veriflow's unified runner:

```powershell
# Preview discovered checks
python skills/veriflow/scripts/run-checks.py . --check openapi

# Execute discovered checks
python skills/veriflow/scripts/run-checks.py . --check openapi --execute
```

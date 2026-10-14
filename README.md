# Veriflow — AI Coding Verification Skill

Veriflow is an open-source verification skill and tool runner designed to help AI coding agents systematically verify code changes after each logical feature batch, diagnose failures honestly, apply minimal repairs within a bounded budget, and re-verify outcomes.

---

## What Veriflow Does

- **Discovers Validation Commands**: Automatically detects project ecosystems (Python, JavaScript/TypeScript, Rust, Go, Java, .NET) and configured test, lint, type-check, and build commands without executing them.
- **Resolves Executables Deterministically**: Prefers project-local virtual environments (`.venv`) and local package tools (`node_modules/.bin`) before falling back to global executables on `PATH`.
- **Safe Opt-In Execution**: Runs checks only when `--execute` is supplied. Executes commands safely with argument lists (`shell=False`) and per-command timeouts.
- **Structured Failure Diagnosis**: Extracts structured diagnostics (`category`, `summary`, `file`, `line`, `rule`, `evidence`) from captured stdout and stderr for Python/pytest tracebacks, ESLint, TypeScript compiler errors, and build tools.
- **Targeted Check Re-Verification**: Enables fast re-verification using `--check <name>` to isolate a single failing check before running the broader suite.
- **Enforces Honest Accounting**: Distinguishes read-only diagnosis from attempted repairs, caps repair attempts at 3, prohibits test weakening or error suppression, and requires post-edit re-execution before claiming success.

---

## Supported Verification Workflow

Veriflow guides the coding agent through a bounded 9-step lifecycle:

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

1. **Discover**: Identify project ecosystems, tools, and commands using `scripts/run-checks.py [target-dir]`.
2. **Preview**: Review discovered checks and rationale in preview mode (default).
3. **Execute**: Run checks only with explicit authorization using `--execute`.
4. **Collect Diagnostics**: Gather structured results (`status`, `diagnostics` array, `stdout`, `stderr`).
5. **Analyze Evidence**: Pinpoint the actionable root cause using verbatim evidence without guessing.
6. **Apply Minimal Fix**: The host AI coding agent applies the smallest reasonable code change using its native editing tools (counts as 1 repair attempt).
7. **Rerun Failing Check**: Re-verify the fix immediately using `--check <name> --execute`.
8. **Rerun Broader Suite**: Run the full project suite by omitting `--check` to catch regressions.
9. **Report**: Emit a standardized completion report distinguishing verified facts from assumptions.

---

## Safety Boundaries & Repair Limits

- **Maximum 3 Repair Attempts**: An agent is capped at 3 file-modifying repair attempts per verification session. Read-only inspection and preview runs never count against the budget.
- **No Test Weakening**: Never delete tests, remove assertions, or disable linter rules (`# noqa`, `// eslint-disable`) to fake passing status.
- **No Speculative Churn**: Stop immediately if evidence is ambiguous, the failure is pre-existing, or fixes would be speculative.
- **Reversion on Regression**: Revert targeted edits if an attempt introduces new failures or breaks other checks.
- **Separation of Concerns**: `run-checks.py` is strictly a verification runner and diagnostic parser. It contains no automatic code editing or self-modification logic. The host AI agent performs all edits.
- **Safety Notice**: Passing verification tests confirms that executed checks succeeded under test conditions; it does not guarantee zero defects, complete security, or deployment readiness.

---

## Usage

### Preview Mode (Default)
Preview available checks and resolved executables without running any commands:
```bash
python skills/veriflow/scripts/run-checks.py [project-dir]
```

### Execution Mode
Explicitly execute discovered checks:
```bash
python skills/veriflow/scripts/run-checks.py [project-dir] --execute
```

### Filter a Specific Check
Preview or execute a single check by name:
```bash
# Preview only the test check:
python skills/veriflow/scripts/run-checks.py [project-dir] --check test

# Execute only the test check:
python skills/veriflow/scripts/run-checks.py [project-dir] --check test --execute
```

### Structured JSON Output
Add `--json` for machine-readable JSON execution reports:
```bash
python skills/veriflow/scripts/run-checks.py [project-dir] --execute --json
```

---

## Browser & User-Journey Verification (Phase 2)

Veriflow includes an incremental browser automation capability designed specifically to catch real client-side defects that AI coding agents commonly introduce:
- Incomplete authentication, broken redirects, and missing error states.
- Bypassed route guards and broken protected pages.
- Session loss on refresh and missing logout invalidation.
- Client-side form validation silence and lost user input.
- Broken navigation links, dead buttons, and 404 recovery.
- Unhandled JavaScript console errors and failed network requests.
- Mobile viewport reflow issues and horizontal scrolling overflow.

### Safety & Tool Detection
- **Playwright is Optional**: Veriflow never requires Playwright as a mandatory dependency. If Playwright or browser binaries are not present, checks report `BLOCKED` with clear remediation commands.
- **Zero Automatic Installation**: Veriflow will never run `pip install` or download browser binaries automatically.
- **Preview-Only by Default**: Like all Veriflow checks, browser verification runs in preview mode by default. Explicit `--execute` authorization is required to launch browsers.
- **Credential Redaction**: Passwords, session cookies, and auth headers are automatically masked (`[REDACTED]`).

### Browser Verification Usage
```bash
# Preview planned journeys via standard runner
python skills/veriflow/scripts/run-checks.py . --check browser

# Execute browser verification via standard runner
python skills/veriflow/scripts/run-checks.py . --check browser --execute

# Standalone runner with target URL
python skills/veriflow/scripts/run-browser-tests.py --url http://localhost:3000 --execute

# Filter by category or journey
python skills/veriflow/scripts/run-browser-tests.py --filter auth --execute
```

---

## Reproducible Demonstrations

Veriflow includes two self-contained, reproducible examples:
1. **Bounded Code Repair**: [`examples/repair-demo/`](examples/repair-demo/) demonstrates automated diagnosis, minimal targeted repair, and re-verification of a broken discount calculation.
2. **Browser Journey Verification & Fault Injection**: [`examples/browser-demo/`](examples/browser-demo/) demonstrates clean execution and deliberate fault injection modes (`--fault broken_login`, `--fault open_protected_route`, `--fault console_error`, etc.) to prove that tests genuinely fail on defective applications.

---

## Production-Readiness Test Catalog

Veriflow includes a research-backed, machine-readable catalog of 135+ production-readiness test cases designed specifically to catch defects in AI-built web applications:
- **Catalog File**: [`skills/veriflow/references/production-test-catalog.json`](skills/veriflow/references/production-test-catalog.json)
- **Catalog Guide**: [`skills/veriflow/references/production-test-catalog-guide.md`](skills/veriflow/references/production-test-catalog-guide.md)

### 15 Operational Coverage Categories
1. **Authentication & Accounts (`AUTH`)**: 15 cases (login valid/invalid/nonexistent, registration, duplicate checks, visibility, forgot password, verification, logout invalidation, session persistence on refresh, token expiry/refresh, deep link redirects, multi-tab sync, submission debouncing).
2. **Routing & Navigation (`ROUTE`)**: 9 cases (direct route loads, nested SPA refresh rewrites, browser history back/forward, 404 page, route guards, URL encoding, redirect loops, link integrity, mobile drawer).
3. **Forms & Input Handling (`FORM`)**: 9 cases (required validation, format checking, boundary length, whitespace trimming, Enter submission, double-click prevention, server parity, data retention on error, file uploads).
4. **Data Integrity & Core Logic (`DATA`)**: 9 cases (full CRUD lifecycle, arithmetic precision, empty states, pagination/virtualization, search/filter idempotency, timezone handling, optimistic rollback, concurrency control, tenant isolation).
5. **Roles & Authorization (`ROLE`)**: 8 cases (anonymous access, privileged route guards, API authorization, IDOR prevention, dynamic role revocation, UI/backend parity, step-up auth, cross-tenant isolation).
6. **API & Integration Reliability (`API`)**: 9 cases (schema contract parity, 4xx handling, 5xx error boundaries, timeout cancellation, offline recovery, defensive JSON parsing, 429 rate limiting, 3rd-party outage fallbacks, missing env vars).
7. **UI Quality & User Experience (`UIUX`)**: 9 cases (dead button detection, 4 view states, horizontal overflow prevention, responsive reflow, modal focus trapping, image fallback, zero console errors, toast deduplication, focus rings).
8. **Accessibility (`A11Y`)**: 9 cases (keyboard-only navigation, visible focus indicators, semantic heading hierarchy, accessible button names, label binding, WCAG AA contrast, live regions, prefers-reduced-motion).
9. **Security (`SEC`)**: 11 cases (XSS input reflection defense, SQL/NoSQL injection prevention, CSRF protection, IDOR verification, open redirect defense, secret scanning in bundles, cookie security flags, HTTP security headers, debug trace suppression, safe file uploads, URL query safety). Grounded in OWASP Cheat Sheets and WSTG.
10. **Performance & Scalability (`PERF`)**: 9 cases (Core Web Vitals LCP/CLS/INP, bundle size budgets, N+1 query detection, DOM node limits, memory leak cleanup, cache headers, DB connection pooling, rate limiting, 100k capacity workload specification).
11. **Resilience & Reliability (`RESL`)**: 8 cases (DB reconnection, frontend backend-outage fallbacks, circuit breakers, exponential backoff with jitter, graceful SIGTERM shutdown, /health & /ready probes, transaction rollback, disaster recovery backup drill).
12. **Deployment & Configuration (`CONF`)**: 8 cases (production build check, env var parity, secret exclusion in git, production base URLs, HTTPS/HSTS enforcement, migration idempotency, asset compression, release smoke checklist).
13. **Search, Metadata & Discoverability (`SEO`)**: 7 cases (title/meta description, canonical tags, robots/sitemap, private route noindex, social OpenGraph/Twitter cards, JSON-LD structured data, semantic 404 status).
14. **Browser & Network Behavior (`NETW`)**: 7 cases (cross-browser engines Chromium/Firefox/WebKit, CORS origin validation, mixed content elimination, 3rd-party script resilience, cookie scope persistence, unhandled rejection handler, offline/slow-3G fallback).
15. **Observability & Post-Deployment (`OBSV`)**: 8 cases (structured JSON logging, correlation IDs X-Request-ID, error telemetry, Four Golden Signals metrics, post-deploy smoke, rollback triggers, alerting rules, release verification report). Grounded in Google SRE Launch Checklist.

### Standardized 7-State Accounting
Every catalog test is classified into: `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`, `NOT_APPLICABLE`, `MANUAL_REVIEW`, or `UNKNOWN`. Missing tests or unavailable tools are never reported as passing.

---

## Running the Veriflow Test Suite

Run Veriflow's test suite using Python's standard library `unittest` or `pytest`:

```bash
# Standard library test runner:
python -m unittest discover tests -v

# Pytest runner:
pytest tests -v
```

All 133 tests across 18 test modules validate project detection, check discovery, execution safety, Windows launchers, local tool discovery, diagnostic parsing, bounded repair specifications, `--check` filtering, the Production-Readiness Test Catalog, browser automation detection, reporter schemas, local demo fixtures, and real browser user journeys.

---

## Known Limitations

- **Host Agent Integration**: Veriflow provides guidance and scripts; integration depends on the host coding agent's skill invocation capabilities unless external hooks are configured.
- **Pre-Existing Failures**: The runner does not inspect Git blame or commit history; pre-existing vs. introduced failures must be triaged by the agent inspecting `git status` / `git diff`.
- **Custom Test Formats**: Non-standard or proprietary test runners emitting unrecognizable output are classified under `UNCLASSIFIED` with raw stdout/stderr preserved for manual agent review.
# Security Verification Demo

A self-contained demonstration of Veriflow's security phase, and more
importantly the evidence that its checks actually detect defects.

A check that passes on correct code proves nothing by itself. What matters is
whether it *fails* when the defect is present. This demo shows both halves of
that pair.

Everything runs on `127.0.0.1` on an OS-assigned port, with fictional accounts
and fixture tokens. No external host is contacted, nothing is installed, and
nothing destructive happens.

## Contents

| File | What it is |
| :--- | :--- |
| `server.py` | A small application served either securely or with one of 9 selectable faults |
| `run-demo.py` | The demo driver: preview, clean baseline, fault injection, static scan |

## 1. Preview: see the checks without running them

```powershell
python examples\security-demo\run-demo.py --preview
```

Starts no server and sends no HTTP request. Preview is a pure function of the
target configuration, which the test suite asserts by patching the request
primitive and confirming it is never called.

## 2. Clean baseline: the secure fixture passes

```powershell
python examples\security-demo\run-demo.py
```

All nine live checks report `PASS` against the secure variant. Exit code 0.

## 3. Fault injection: prove each check detects its defect

```powershell
python examples\security-demo\run-demo.py --fault reflected_xss
python examples\security-demo\run-demo.py --fault cross_user_leak
python examples\security-demo\run-demo.py --fault stack_trace_leak
```

Each fault breaks exactly one behaviour. The matching check fails with a
specific diagnosis, structured diagnostics and a remediation. Exit code 1.

| Fault | Breaks | Check that must fail |
| :--- | :--- | :--- |
| `missing_headers` | sends no security headers | `SEC-LIVE-HEADERS-001` |
| `insecure_cookie` | session cookie without HttpOnly/SameSite | `SEC-LIVE-COOKIE-001` |
| `reflected_xss` | reflects input into HTML unencoded | `SEC-LIVE-XSS-001` |
| `open_protected_route` | serves a protected path anonymously | `SEC-LIVE-AUTH-001` |
| `cross_user_leak` | authenticates the caller but never checks ownership | `SEC-LIVE-IDOR-001` |
| `stack_trace_leak` | returns a traceback containing a connection password | `SEC-LIVE-ERROR-001` |
| `secret_in_response` | embeds an API key in the public response | `SEC-LIVE-SECRET-001` |
| `open_redirect` | honours an externally supplied redirect destination | `SEC-LIVE-REDIRECT-001` |
| `missing_csrf` | accepts a state-changing POST with no token | `SEC-LIVE-CSRF-001` |

## 4. The full detection matrix

```powershell
python examples\security-demo\run-demo.py --all-faults
```

Runs the clean baseline and all nine faults in sequence, and reports for each
one whether the expected check failed and whether any unrelated check failed
with it. Collateral failures matter: a report where one defect lights up five
checks is a report nobody can act on.

Exit code 0 only when the clean fixture passes **and** every fault is detected.

## 5. Static scan: vulnerable versus corrected

```powershell
python examples\security-demo\run-demo.py --static
```

Scans a file carrying one defect per category, then the same file corrected.
Vulnerable: 6 findings. Corrected: 0.

Note what the vulnerable report shows for the hard-coded password:

```
Evidence:    DB_PASSWORD = "Kf...[REDACTED:20 chars]"
```

The scanner reports the location and the shape, never the value. The test suite
asserts the secret appears nowhere in the finding, the JSON report or the text
report.

## JSON output

```powershell
python examples\security-demo\run-demo.py --all-faults --format json
```

## What this demo does not show

- **Dependency CVE auditing.** Veriflow bundles no vulnerability database. Run
  `pip-audit`, `npm audit` or `cargo audit` and treat their output as evidence.
- **Stored or DOM-based XSS.** These checks issue single stateless requests and
  execute no page JavaScript.
- **A penetration test.** The probes are inert, non-destructive and
  loopback-bound. A clean security phase is not a security assessment.

`skills/veriflow/references/security-test-mapping.json` records, per check,
exactly what it covers and what it explicitly does not.

## Safety notes on the fixture itself

`server.py` deliberately contains credential-shaped literals and, in fault
mode, serves a leaked key and a traceback. They are fixture data: every one
carries the inline `veriflow: allow-security` marker, and the file is listed in
the repository's `.veriflow-security-ignore` so a scan of Veriflow reports them
as suppressed rather than as findings. The suppression count is always
disclosed in the report.

Passing a fault name that does not exist raises an error rather than quietly
starting a secure server, so a typo in a test cannot produce a false pass.

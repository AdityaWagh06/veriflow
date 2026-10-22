# Veriflow Diagnostics Reference

Read this when you have an error message and need to work out what is actually
wrong.

**An error message is a clue, not a diagnosis.** The same text has different
causes, and the most common cause is not always yours. Every entry below gives
the evidence that separates the possibilities, because applying the usual fix to
an unusual cause is how a narrow bug becomes a broad one.

Format for each entry: the symptom as it appears, the causes worth considering,
the evidence that distinguishes them, the safe fix, the regression test, and the
cases where the same symptom means something else.

Patterns, with their root-cause hypotheses in machine-readable form, are in
[`failure-patterns.json`](failure-patterns.json).

---

## How to use an error message

1. **Read the whole output, not the last line.** The first error is usually the
   real one; the rest are consequences.
2. **Count the distinct failures.** Fixing the first and stopping is a common
   and costly mistake.
3. **Note which process produced it**, with which interpreter, in which working
   directory. Most environment errors are answered by those three facts.
4. **Separate the location from the cause.** A traceback says where execution
   stopped. The decision that made it stop is often elsewhere.
5. **Reduce it.** The smallest input that still fails tells you more than the
   full stack trace.

---

## Python

### `SyntaxError` / `IndentationError`

**Symptom:** The file fails to parse. The reported line is where the parser gave
up, which is frequently *after* the real mistake.

**Causes:** an unclosed bracket, parenthesis or quote on an earlier line; a
missing colon; mixed tabs and spaces; a merge conflict marker left in the file;
syntax valid only in a newer Python than the interpreter running.

**Evidence:** read upward from the reported line to the last balanced bracket.
Check `python --version` against the syntax used. Search the file for `<<<<<<<`.

**Safe fix:** correct the structure. Never silence it by reformatting the whole
file: that hides the change in noise.

**Regression test:** a collection-time smoke test, so a parse error fails the
suite immediately rather than at first use.

**Different cause, same symptom:** a `SyntaxError` naming a library file means
the library was built for a different Python version, not that your code is
wrong.

### `NameError: name 'X' is not defined`

**Causes:** a typo; a name defined in another scope; an import that was removed
or never added; a name used before assignment; a name that only exists under a
conditional import.

**Evidence:** search the file for the definition. Check whether the import is
inside a `try`, an `if TYPE_CHECKING:` block, or a function. Confirm the
assignment runs on the path taken.

**Safe fix:** define or import it. Do not add a module-level default to silence
it; that converts a crash into a wrong answer.

**Different cause:** inside a comprehension or a nested function, this is often
a scoping rule rather than a missing definition.

### `ModuleNotFoundError` / `ImportError: cannot import name`

**Causes:** the package is not installed in *this* interpreter; the import name
differs from the distribution name; the symbol moved between versions; the path
is wrong relative to the working directory; the wrong virtual environment is
active; a circular import; the module does not exist at all.

**Evidence:** this is the single most important distinction to make, and the
evidence is cheap:

```powershell
python -c "import sys; print(sys.executable); print(sys.path)"
python -c "import X; print(X.__file__, getattr(X, '__version__', 'n/a'))"
pip show <distribution-name>
```

For a circular import, the traceback names both modules in the cycle, and the
message usually says *"most likely due to a circular import"*.

**Safe fix:** correct the import to a symbol that exists in the installed
version, or add a verified, pinned dependency and say why. For a cycle, move the
shared piece into a third module or defer the import into the function.

**Regression test:** import every public entry point in one test.

**Different cause, same symptom:** if the package *is* installed and the symbol
*is* documented, you are probably reading documentation for a different major
version. Check the installed version's own source. See
[`failure-patterns.json`](failure-patterns.json) `VFP-ENV-001` before installing
anything you have not verified on its registry.

### `TypeError` / `AttributeError` on `None`

**Symptom:** `'NoneType' object has no attribute 'X'`, or `is not subscriptable`,
or `is not iterable`.

**Causes:** a function returned `None` on a path you did not expect; a lookup
missed and returned `None`; a function with no `return` on one branch; an
in-place method whose return value you used (`list.sort()` returns `None`).

**Evidence:** find where the `None` originated, not where it was used. Whether
the value can *legitimately* be absent decides the fix: if it can, handle it; if
it cannot, the bug is upstream.

**Safe fix:** handle the absence at the boundary where the value enters, or fix
the upstream function that should not have returned `None`.

**Regression test:** a case that exercises the path producing `None`.

**Different cause:** on an object you constructed, this often means `__init__`
returned early or an attribute is only set on some paths.

### `KeyError` / `IndexError`

**Causes:** the key or index genuinely is not there; an off-by-one at the
boundary; a key whose name changed; an empty collection taking a non-empty path.

**Evidence:** print the actual keys or the actual length at the failure point.
Do not assume the shape.

**Safe fix:** use an explicit default where absence is valid (`dict.get`), or fix
the producer where it is not. Never wrap the block in a bare `except`.

**Different cause:** a `KeyError` from a configuration or environment lookup is
a missing-configuration problem, not a code problem. The fix is to document and
validate the required variable at startup.

### `RuntimeWarning: coroutine 'X' was never awaited`

**Causes:** a missing `await`; a coroutine passed where a callable was expected;
a task created and never awaited.

**Evidence:** the warning names the coroutine. Check whether the async test
framework is configured at all: if it is not, the test never ran.

**Safe fix:** await it, or retain the task and await it where the result matters.
Never suppress the warning.

**Different cause:** if the failure is *intermittent* rather than warned, it is a
race, and adding `await` will not fix it. See `VFP-CORRECT-004`.

### `PermissionError` / `FileNotFoundError`

**Causes:** a relative path resolved against a different working directory; a
file the process genuinely cannot read; a directory that does not exist yet; on
Windows, a file held open by another process.

**Evidence:** print `Path.cwd()` and the fully resolved absolute path from inside
the failing process. Most "file not found" errors are working-directory errors.

**Safe fix:** resolve paths relative to a known anchor (the module file, or an
explicit root), and create parent directories explicitly.

**Regression test:** run the test from a different working directory. A test that
only passes from the repository root has a hidden dependency.

**Different cause:** `PermissionError` on a path that exists and is readable is,
on Windows, usually a file lock rather than an access-control problem.

---

## JavaScript and TypeScript

### `Cannot find module 'X' or its corresponding type declarations`

**Causes:** the package is not installed; types ship separately (`@types/X`); a
path alias configured in `tsconfig.json` but not in the bundler, or the reverse;
a case-sensitivity difference that works on Windows and fails in CI.

**Evidence:** `npm ls X`. Check whether `node_modules/X` exists. Compare the
alias configuration in `tsconfig.json` against the bundler's. Compare the import
path's casing against the file on disk, character by character.

**Safe fix:** install the package or its types; make alias configuration agree
across tools; correct the casing.

**Different cause, same symptom:** a module that resolves locally and fails in CI
is almost always casing, because Windows and macOS default to case-insensitive
filesystems and Linux does not.

### `TypeError: Cannot read properties of undefined (reading 'X')`

**Causes:** data not yet loaded on first render; an API response shaped
differently from what the code assumes; an optional field accessed without a
guard; an array index that does not exist.

**Evidence:** the actual response body, not the type you declared for it. A
TypeScript type is a compile-time claim, and `any` or a cast makes it unchecked
at runtime.

**Safe fix:** guard the access, render an explicit loading state, and validate
the response shape at the boundary where it enters.

**Regression test:** a test with the loading state and the absent-field case.

**Different cause:** during server-side rendering this often means a browser-only
API was touched on the server.

### Unhandled promise rejection

**Causes:** a promise with no `.catch` and no enclosing `try`/`await`; a rejection
inside a `.then` with no handler; a fire-and-forget async call.

**Evidence:** the warning names the rejection value. Attach a global handler
temporarily to get the stack.

**Safe fix:** handle the rejection where the failure is meaningful. Never
`.catch(() => {})`: that is the swallowed-error pattern, which a Veriflow scan
reports as `SEC-ERR-001`.

### Hydration mismatch

**Symptom:** a warning that server-rendered markup did not match the client.

**Causes:** a render depending on `Date.now()`, a random value, `localStorage`,
`window`, or a timezone; markup differing between the two paths; invalid nesting
the browser silently corrects.

**Evidence:** the warning names the differing text or attribute. Ask whether the
value *could* be identical on both sides. If not, it does not belong in shared
render output.

**Safe fix:** move the value out of the shared render path, or render it only
after mount.

**Different cause:** invalid HTML nesting produces this warning even when the
data is identical, because the browser restructures the DOM.

### Package manager and lockfile errors

**Symptom:** peer dependency conflicts, `ERESOLVE`, a lockfile that will not
install, or an integrity checksum failure.

**Causes:** two package managers used in one project (`package-lock.json` and
`pnpm-lock.yaml` both present); a lockfile edited by hand; a hoisting difference
between managers; a registry or proxy difference.

**Evidence:** list the lockfiles present. Exactly one should be. Check whether
`packageManager` is declared in `package.json`.

**Safe fix:** pick one package manager, delete the other lockfiles, and
regenerate. Never hand-edit a lockfile.

**Different cause:** an integrity failure can indicate a tampered or
proxy-rewritten artefact, not just a stale lockfile. Investigate before
regenerating past it.

---

## HTTP status codes

A status code tells you how the server classified the request, which is not
always how it actually failed.

| Status | Usually means | Also check |
| :--- | :--- | :--- |
| **400** | Malformed request or failed validation | Which field failed, and whether the error body says so usefully |
| **401** | No or invalid credential | Whether the credential was sent at all; a CORS preflight can strip it |
| **403** | Authenticated but not permitted | Whether this is *missing* authorization or *correct* denial. A 403 where 200 is expected may be an authorization bug, not a client bug |
| **404** | No such route or resource | Whether the route exists but the method does not; whether it is a deliberate 404 hiding a 403 |
| **405** | Method not allowed on an existing route | The `Allow` header. Often a trailing-slash or route-definition mismatch |
| **409** | Conflict | A duplicate submission, or an optimistic-concurrency failure |
| **413** | Payload too large | The limit at the proxy *and* in the application; they often differ |
| **415** | Unsupported media type | Whether `Content-Type` was sent at all |
| **422** | Semantically invalid | Framework-dependent; some use 400 for the same condition |
| **429** | Rate limited | The `Retry-After` header, and whether your client honours it |
| **500** | Unhandled server error | The *server log*, not the response body. A body with detail in it is a disclosure defect (`VFP-API-003`) |
| **502** | Upstream returned something invalid | Whether the upstream crashed or the proxy misconfigured |
| **503** | Unavailable or deliberately shedding load | Whether this is graceful degradation (correct) or a crash loop |
| **504** | Upstream timed out | The timeout at each hop. The shortest one wins, and it is often not the one you set |

**Diagnostic sequence for any unexpected status:**

1. Capture the full request: method, path, headers, body.
2. Capture the full response: status, headers, body.
3. Reproduce it against a local instance, outside the browser, to remove CORS
   and caching from the picture.
4. Only then read the server log for the same request.

### CORS failures

**Symptom:** a browser console error about a blocked cross-origin request, often
with a status of `0` and an empty response.

**Key point:** CORS is enforced by the browser, not the server. The request may
well have succeeded. The same request from `curl` will work, which proves
nothing about the browser case.

**Causes:** no `Access-Control-Allow-Origin` on the response; a wildcard origin
combined with credentials, which browsers reject; the preflight `OPTIONS` not
handled; a requested header not listed in `Access-Control-Allow-Headers`.

**Evidence:** the preflight `OPTIONS` response headers, not the main request's.

**Safe fix:** list the exact origins and the headers used. A wildcard origin is
flagged by `SEC-CONF-002` and is wrong wherever credentials are accepted.

### Cookie and session problems

**Symptom:** login appears to succeed, then the next request is unauthenticated.

**Causes:** `SameSite` blocking the cookie on a cross-site request; `Secure` set
while serving over HTTP; a domain or path too narrow; the client not sending
credentials; the cookie larger than the browser's limit.

**Evidence:** the actual `Set-Cookie` header from the login response, and whether
the cookie appears in the next request. Check `SEC-LIVE-COOKIE-001` output.

**Different cause:** if the cookie *is* sent and still rejected, the problem is
session storage or validation on the server, not the cookie.

### Connection errors

| Symptom | Usually means |
| :--- | :--- |
| Connection refused | Nothing is listening on that port. Check the port and that the process started |
| Connection reset | The peer closed mid-exchange. Often a protocol mismatch, such as HTTP to an HTTPS port |
| Timeout | Reached but no response in time. Check each hop's timeout |
| DNS resolution failure | The name does not resolve from *this* host. Check `/etc/hosts`, split-horizon DNS, container networking |
| TLS certificate error | Expired, wrong hostname, or an untrusted private CA. Never fix this by disabling verification: `SEC-TLS-001` flags that |

---

## SQL and databases

### Syntax error near an unexpected token

**Causes:** a reserved word used unquoted as an identifier; dialect differences;
a string value containing a quote, spliced rather than bound.

**Evidence:** log the statement *as sent*, with parameters shown separately. If
the parameters are embedded in the statement text, you have found an injection
site, not just a syntax error. See `VFP-SEC-001`.

**Safe fix:** parameterise. That fixes both the syntax error and the
vulnerability.

### Constraint violation

| Violation | Means | Check |
| :--- | :--- | :--- |
| Unique | A row with that value exists | Whether this is a duplicate submission, a race between two inserts, or a genuine conflict to report |
| Foreign key | The referenced row is absent | Insert order; whether a cascade deleted it |
| Not null | A required column had no value | Whether the default is missing or the writer is |
| Check | A value outside the allowed set | Whether the application validates the same rule |

A unique violation under concurrency is a race, not a validation gap: two
requests both checked, both saw nothing, and both inserted. The fix is a
database constraint plus handling the violation, not an earlier check.

### Deadlock detected

**Causes:** two transactions acquiring the same locks in different orders; a
long transaction holding locks; lock escalation from row to table.

**Evidence:** the database's own deadlock report, which names both transactions
and the locks. Retry only after reading it: a retry loop over an ordering bug
burns capacity without fixing anything.

**Safe fix:** acquire locks in a consistent order, shorten transactions, and
retry on deadlock as a secondary measure.

### Connection pool exhausted

**Causes:** connections not returned (a missing context manager or `close`); the
pool too small for the concurrency; a long query holding connections; a leak in
one path under load.

**Evidence:** the pool's in-use count over time, and which code path holds them.
Raising the pool size hides a leak rather than fixing it.

**Safe fix:** return connections deterministically with a context manager. Resize
the pool only once you have ruled out a leak.

---

## Build, container and CI

### The build succeeds locally and fails in CI

**Causes, in the order worth checking:**

1. **Case sensitivity.** An import whose casing differs from the file. Works on
   Windows and macOS, fails on Linux.
2. **An uncommitted file.** It exists locally and is not in the repository.
3. **A different dependency version.** CI installs from the lockfile; your
   machine may not have.
4. **A missing environment variable.** Set in your shell, absent in CI.
5. **A different runtime version.** Compare the exact version, not the major.
6. **Path separators.** A hard-coded `\` or `/`.

**Evidence:** print the runtime version, the resolved dependency versions and the
relevant environment variables *in the CI job*, and compare against the same
locally. Guessing is slower than printing.

### Docker build or startup failure

| Symptom | Causes |
| :--- | :--- |
| Build fails at a `COPY` | The path is outside the build context, or excluded by `.dockerignore` |
| Build succeeds, container exits immediately | The entrypoint failed. Read the container log, not the build log |
| "port is already allocated" | Another container or process holds it |
| Permission denied inside the container | The image runs as a non-root user without access to a mounted path |
| Works locally, fails in the registry pull | Architecture mismatch (arm64 image on amd64 host) |
| Health check fails while the app looks fine | The check targets the wrong port, path or interface — often `localhost` inside a container that binds `0.0.0.0` |

**Evidence:** the container's own logs and its exit code. An exit code of 0 with
an immediate stop means the process completed rather than served.

### Deployment reports success while the application is unhealthy

This is the most dangerous build-stage failure, because every signal is green.

**Causes:** the health check passes before the application is ready, or checks
only that the process is alive; migrations ran at startup and failed silently; a
required variable is absent and the code fell back to a default; the readiness
probe does not test a dependency.

**Evidence:** make one real request through the full path a user would take. A
passing deployment pipeline is not evidence that the application works.

**Safe fix:** make readiness depend on the dependencies the application actually
needs, and validate required configuration at startup by failing fast rather
than defaulting.

---

## Veriflow's own diagnostic states

When `run-checks.py --execute` reports a non-`PASS` status:

| Status | What it means | What to do |
| :--- | :--- | :--- |
| `FAIL` | Executed, non-zero exit | Read the `diagnostics` array: category, file, line, rule, verbatim evidence |
| `TIMEOUT` | Exceeded the per-command timeout | Look for an infinite loop, a hanging request or a deadlock introduced by the change. If the suite is simply large, raise `--timeout`; do not rewrite valid logic to beat the clock |
| `COMMAND_NOT_FOUND` | The tool is not installed or not resolvable | Report it. Do not modify code to bypass it, and do not install it without authorization |
| `ERROR` | An OS or execution error | Usually a path, permission or working-directory problem |
| `UNCLASSIFIED` | Non-zero exit, output matching no known signature | **Do not guess.** Read the raw stdout and stderr. If the failure cannot be attributed to the change with confidence, stop and report the raw evidence |
| `BLOCKED` | A prerequisite is unavailable | Say what the check would have covered. If it covers the change, the honest status is `PARTIALLY_VERIFIED` |

Diagnostic categories the runner parses: `TEST_ASSERTION_FAILURE`,
`PYTHON_TRACEBACK`, `SYNTAX_ERROR`, `LINT_VIOLATION`, `TYPE_ERROR`,
`BUILD_ERROR`, `IMPORT_OR_MODULE_ERROR`, `UNCLASSIFIED`.

### Pre-existing failures

Before treating a failure as yours, check `git stash` or a clean checkout. A
failure present before your change is not caused by it, and fixing it is a
separate piece of work that belongs in its own change. Document it; do not
quietly absorb it.

---

## What this reference is not

It covers recurring, recognisable patterns. It is not a catalogue of every error
message, and no such catalogue would help: the value is in the evidence that
separates causes, not in the volume of symptoms listed.

When a message is not here, the method still applies. Identify the process, the
interpreter and the working directory. Reduce the input. Separate where it
stopped from what decided to stop. And when the evidence does not support a
conclusion, report `UNKNOWN` rather than the most plausible-sounding guess.

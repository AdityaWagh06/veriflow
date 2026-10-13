# Veriflow End-to-End Repair Demonstration

This example preserves the end-to-end diagnostic and repair demonstration performed during Veriflow's development. It illustrates how Veriflow discovers project validation commands, captures structured diagnostics on test failures, guides the host AI coding agent to apply a minimal code fix, and verifies the repair using targeted check filtering (`--check`).

## Committed State

This directory contains the **final, verified, passing state** of the demonstration project:
- [`math_ops.py`](math_ops.py): Application module with the corrected discount calculation.
- [`tests/test_math_ops.py`](tests/test_math_ops.py): Pytest test suite covering standard, zero, and full discount scenarios.
- [`pyproject.toml`](pyproject.toml): Minimal pytest configuration setting `pythonpath = ["."]`.

---

## The Demonstrated Bug and Repair Lifecycle

### 1. The Original Bug
In `math_ops.py`, the `calculate_discount` function originally had an addition sign instead of subtraction:

```python
# Original buggy implementation:
def calculate_discount(price: float, discount_percent: float) -> float:
    ...
    return round(price + (price * discount_percent / 100.0), 2)
```

### 2. The Failing Test
When `test_calculate_discount_standard()` ran with `price = 100.0` and `discount_percent = 20.0`:
- **Expected**: `80.0`
- **Actual**: `120.0`
- **Assertion**: `assert calculate_discount(100.0, 20.0) == 80.0` failed with `assert 120.0 == 80.0`.

### 3. Veriflow Diagnostic Output
When executed via `python skills/veriflow/scripts/run-checks.py <dir> --execute --json`, Veriflow diagnosed the failure without guessing:

```json
{
  "category": "TEST_ASSERTION_FAILURE",
  "summary": "Assertion failure in test_calculate_discount_standard: assert 120.0 == 80.0",
  "file": "tests/test_math_ops.py",
  "evidence": "FAILED tests/test_math_ops.py::test_calculate_discount_standard - assert 120.0 == 80.0"
}
```

### 4. The Targeted Repair (Attempt 1 of 3)
Guided by the structured diagnostic, the agent applied a minimal one-character fix to application code (`+` changed to `-`):

```diff
--- a/math_ops.py
+++ b/math_ops.py
@@ -10,3 +10,3 @@
-    return round(price + (price * discount_percent / 100.0), 2)
+    return round(price - (price * discount_percent / 100.0), 2)
```

The test file (`tests/test_math_ops.py`) remained completely unchanged.

### 5. Targeted Re-Verification
The agent immediately reran the specific failing check using `--check test`:

```bash
python skills/veriflow/scripts/run-checks.py examples/repair-demo --check test --execute
```
**Outcome**: `[PASS]` (exit code `0`, `0.5s`).

### 6. Broader Suite Verification
Once the targeted check passed, the agent ran the broader suite across the project:

```bash
python skills/veriflow/scripts/run-checks.py examples/repair-demo --execute
```
**Outcome**: `[PASS]` on all checks.

---

## How to Safely Reproduce the Failure

To reproduce the failure without modifying this repository:

1. **Copy this directory to a temporary location**:
   ```bash
   cp -r examples/repair-demo /tmp/disposable-demo
   # or on Windows PowerShell:
   Copy-Item -Recurse examples/repair-demo C:\temp\disposable-demo
   ```

2. **Introduce the bug in `math_ops.py`**:
   Change line 12 in the disposable copy:
   ```python
   return round(price + (price * discount_percent / 100.0), 2)
   ```

3. **Run Veriflow against the broken copy**:
   ```bash
   # Preview mode (read-only):
   python skills/veriflow/scripts/run-checks.py C:\temp\disposable-demo

   # Execution mode:
   python skills/veriflow/scripts/run-checks.py C:\temp\disposable-demo --execute
   ```
   Observe the `[FAIL]` status and `TEST_ASSERTION_FAILURE` diagnostic.

4. **Apply the fix and verify**:
   Restore `-` in `math_ops.py`, then run:
   ```bash
   python skills/veriflow/scripts/run-checks.py C:\temp\disposable-demo --check test --execute
   ```
   Observe the clean `[PASS]`.

---

## Verifying This Example

To verify the committed example directly:

```bash
# Preview:
python skills/veriflow/scripts/run-checks.py examples/repair-demo

# Execution:
python skills/veriflow/scripts/run-checks.py examples/repair-demo --execute
```
Both commands exit with code `0`.
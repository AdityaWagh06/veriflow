---
name: veriflow
description: Verify AI-generated code changes by running relevant project checks, diagnosing failures, applying minimal fixes, and confirming results. Use when implementing features, modifying existing code, fixing bugs, or preparing a project for release.
---

# Veriflow — AI Coding Verification Skill

## Purpose

Do not treat code as complete merely because it has been written.

Verify that changes work, preserve existing behavior, and meet the project's established quality standards.

## Invocation and Architecture

Veriflow provides structured verification guidance accompanied by automation scripts located within the skill directory:

- **Project Detector**: `scripts/detect-project.py`
  Discovers project ecosystems (Python, JavaScript, TypeScript, Rust, Go, .NET), package managers, and configured npm/project scripts.
- **Verification Runner**: `scripts/run-checks.py`
  Discovers available validation commands from project configurations (preview by default) and optionally executes them via `--execute`.
- **Reference Checklist**: `references/verification-checklist.md`
  Detailed checklist for change reviews, routing, security, and release readiness.

> **Note on Agent Integration**:
> Coding agents and automation environments do not all trigger skills automatically. Agents and developers must invoke these scripts explicitly when verifying changes, unless an external runner or hook has been configured. Always reference scripts relative to the installed skill directory.

---

## Core Workflow

Before starting the workflow, read `references/verification-checklist.md`. Apply only the checks relevant to the current project and changes.

Follow this workflow whenever implementing a feature, fixing a bug, or modifying existing code.

### 1. Inspect Before Changing

1. **Inspect project instructions and Git status**:
   - Read relevant project instructions (`AGENTS.md`, `README.md`, contributor guidelines).
   - Inspect the working tree (`git status`, `git diff`) to identify existing user work. Never overwrite or discard unrelated changes.
2. **Run project detection**:
   Invoke the detection script on the target project directory:
   ```bash
   python <path-to-skill>/scripts/detect-project.py [target-project-dir]
   ```
   Inspect the output for identified languages, frameworks, package managers, and defined package scripts.

### 2. Plan a Small Feature Batch

- Break work into small, logically complete feature batches.
- Identify affected files and likely regression risks.
- Define what checks must pass before declaring the batch complete.
- Prefer focused changes over wide-ranging refactors.

### 3. Implement Focused Changes

- Follow existing naming, architectural, and error-handling patterns.
- Avoid unrelated refactoring or changing unrequested files.
- Handle expected errors and edge cases defensively.
- Never hardcode credentials, secrets, or API keys.
- Never weaken security controls or test assertions simply to make checks pass.

### 4. Verify After Each Logical Feature Batch

Verification follows a two-stage approach: **Discovery Preview** followed by **Explicit Execution**.

#### Stage 4A: Run Discovery Preview
Always preview available checks before running commands:
```bash
python <path-to-skill>/scripts/run-checks.py [target-project-dir]
```
Add `--json` for machine-readable output:
```bash
python <path-to-skill>/scripts/run-checks.py [target-project-dir] --json
```
- Review the proposed checks, resolved executables, and discovery rationale (e.g., pytest, ruff, mypy, npm scripts, cargo test).
- Inspect the resolution source:
  1. **Project Virtual Environment** (`.venv`, `venv`, `env`): Python tools preferred via `python -m <tool>`.
  2. **Project Node Modules** (`node_modules/.bin`): Local ESLint, TypeScript (`tsc`), etc.
  3. **Project Root Scripts**: Direct project wrappers (e.g. `gradlew.bat`, `mvnw`).
  4. **System PATH**: Global executables via `shutil.which` when project-local tools are absent.
  5. **Not Found**: Unresolved tools reported in limitations and evaluated as `COMMAND_NOT_FOUND` on execution.
- Review listed limitations (e.g., missing linters or absent test suites).
- Never assume an unlisted check exists or that an absent tool is installed.

#### Stage 4B: Execute Relevant Checks Explicitly
Execute the discovered validation commands using the `--execute` flag:
```bash
python <path-to-skill>/scripts/run-checks.py [target-project-dir] --execute
```
Optional flags:
- `--timeout SECONDS`: Set a custom per-command timeout (default: 30 seconds).
- `--json`: Emit a structured execution report with stdout, stderr, exit codes, and parsed `diagnostics`.

The runner evaluates each command safely without shell strings (`shell=False`), tracks process duration, and classifies outcomes into:
- `PASS`: Process exited successfully with code 0.
- `FAIL`: Process exited with a non-zero code.
- `TIMEOUT`: Process exceeded the per-command execution timeout.
- `COMMAND_NOT_FOUND`: Executable is not installed on PATH or in the project.
- `ERROR`: Operating system or execution error.

Each failing or anomalous check includes a structured `diagnostics` array containing extracted error locations, rule IDs, and verbatim evidence.

If the user requested multiple feature batches, verify each batch before moving to the next.

### 5. Bounded AI-Guided Repair and Re-Verification Lifecycle

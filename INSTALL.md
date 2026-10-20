# Installing Veriflow

Veriflow is a Claude Code skill. Claude Code discovers skills in exactly two
places:

| Scope | Location | Applies to |
| :--- | :--- | :--- |
| **Project** | `<project>/.claude/skills/veriflow/SKILL.md` | that one repository |
| **Personal** | `~/.claude/skills/veriflow/SKILL.md` | every project you open |

On Windows, `~` is `%USERPROFILE%`, so the personal path is
`C:\Users\<you>\.claude\skills\veriflow\SKILL.md`.

Veriflow's source lives at `skills/veriflow/`, which Claude Code does **not**
scan. Installing means copying that directory into one of the two paths above.

---

## Requirements

- **Python 3.9 or newer.** Veriflow is pure standard library; nothing to install
  for the core engines, project detection, the verification runner, the static
  security scanner, or the API and OpenAPI engines.
- **Claude Code**, if you want Veriflow as a skill. The scripts also work
  standalone from a terminal.

Two optional dependencies, each needed only for one capability:

| Package | Enables | Without it |
| :--- | :--- | :--- |
| `playwright` | browser and user-journey checks | those checks report `BLOCKED` with remediation |
| `PyYAML` | YAML OpenAPI specifications | YAML specs report `BLOCKED`; JSON specs still work |

Veriflow never installs a package for you.

```powershell
# Only if you want the optional capabilities:
pip install -r requirements-optional.txt
python -m playwright install chromium   # browser binaries, a separate step
```

---

## Install

### Project installation (one repository)

Use this when a team should get Veriflow by cloning the repo.

```powershell
git clone https://github.com/AdityaWagh06/Veriflow.git
cd Veriflow

python install.py --project --dry-run   # see exactly what will be written
python install.py --project             # write it
```

To install into a *different* project:

```powershell
python D:\Veriflow\install.py --project --project-root C:\work\my-app
```

That creates `C:\work\my-app\.claude\skills\veriflow\`. Commit it if you want
your team to get the skill automatically; add it to `.gitignore` if not.

### Personal installation (all your projects)

```powershell
python install.py --personal --dry-run
python install.py --personal
```

This writes `~/.claude/skills/veriflow/` and nothing else. It does **not**
change any Claude Code setting, registry key, `PATH` entry or environment
variable.

### What the installer will not do

- It never runs without `--project` or `--personal`. There is no default
  destination.
- It never overwrites a `veriflow` skill directory it did not create. If one
  exists without Veriflow's `.veriflow-install.json` marker, the installer stops
  and tells you your options. `--force` replaces it, and keeps a timestamped
  backup next to it first.
- It never touches a sibling skill.
- `--dry-run` writes nothing, ever.

---

## Confirm Claude Code found it

1. **Restart Claude Code**, or start a new session. Skills are scanned at
   session start, so an installation mid-session is not visible until then.

2. **Check the installation itself:**

   ```powershell
   python install.py --project --verify
   # or
   python install.py --personal --verify
   ```

   This confirms `SKILL.md` exists with valid frontmatter, that every required
   script and reference is present, and that the installed copy is not out of
   date relative to the source. Exit code 0 means OK.

3. **Ask Claude Code:**

   > what skills do you have available?

   `veriflow` should be listed.

4. **Invoke it.** You do not call a skill by name. Describe the work and Claude
   loads the skill when its description matches:

   > I changed the login handler. Verify it.

   > Run Veriflow's security scan over this project.

   > The build is failing. Diagnose it before changing anything.

---

## Run a safe demo

Every command below is read-only or preview-only. None of them executes project
code or opens a network connection unless the text says so.

```powershell
# 1. What does Veriflow see in this project?
python skills\veriflow\scripts\detect-project.py .

# 2. What checks exist? (discovery only, nothing runs)
python skills\veriflow\scripts\run-checks.py .

# 3. Static security scan (read-only, offline, no prerequisites)
python skills\veriflow\scripts\run-security-tests.py .

# 4. The bounded-repair demo: a deliberately broken project
python skills\veriflow\scripts\run-checks.py examples\repair-demo
type examples\repair-demo\README.md
```

Demos that execute something, each self-contained on a loopback port:

```powershell
# API verification against a local fixture server
python examples\api-demo\run-demo.py

# OpenAPI contract verification
python examples\openapi-demo\run-demo.py --preview
python examples\openapi-demo\run-demo.py

# Live security checks against the local security fixture
python examples\security-demo\run-demo.py --preview
python examples\security-demo\run-demo.py
```

Run the test suite:

```powershell
pip install -r requirements-dev.txt
python -m pytest tests -q
```

---

## Troubleshooting

### Claude Code does not list the skill

1. Confirm the file is where Claude Code looks:
   ```powershell
   dir .claude\skills\veriflow\SKILL.md
   dir $env:USERPROFILE\.claude\skills\veriflow\SKILL.md
   ```
2. Run `python install.py --project --verify`. It names the specific problem.
3. Start a **new session**. Skills are scanned once, at session start.
4. Check the frontmatter is intact. `SKILL.md` must begin with `---` on line 1,
   and contain `name:` and `description:` before the closing `---`.
5. Confirm you are in the project you installed into. A project installation
   only applies to that directory tree.

### "Python package 'playwright' is not installed"

Expected, and not an error. Browser checks report `BLOCKED` and everything else
continues. Install it only if you want browser journeys:

```powershell
pip install playwright
python -m playwright install chromium
```

### "PyYAML is not installed" on a YAML OpenAPI spec

Either `pip install pyyaml`, or convert the spec to JSON. JSON specs need
nothing.

### A check reports `COMMAND_NOT_FOUND`

The tool genuinely is not installed, or not where Veriflow looked. The preview
output names the resolution source it tried (`project_venv`, `node_modules`,
`project_script`, `system_path`, `not_found`). Install the tool, or activate the
right virtual environment, and rerun. Veriflow will not install it for you.

### The security scan reports findings in my test fixtures

Expected if those files deliberately contain vulnerable samples. Exclude them,
and the report will disclose that it did:

```powershell
python skills\veriflow\scripts\run-security-tests.py . --exclude "tests/fixtures/*"
```

Or commit a `.veriflow-security-ignore` file at your project root, one path glob
per line. Veriflow's own repository has one; use it as a template. Exclusions
are always reported, never silent.

For a single line, add the inline marker `veriflow: allow-security` in a
comment. Suppressed findings are counted and disclosed in the report.

### `install.py` refuses to overwrite

There is already a `veriflow` skill directory that Veriflow did not install.
Look at it first. Then either `--force` (which backs it up), install to the
other scope, or move it aside yourself.

### Permission denied

You cannot write to the destination. Choose the other scope, or fix the
directory's permissions. Veriflow does not need and does not request elevation.

---

## Update

```powershell
cd Veriflow
git pull
python install.py --project    # or --personal
```

The installer reports what it added, updated and removed, deletes files that no
longer exist in the new version, and says "Already up to date" when there is
nothing to do. Restart Claude Code afterwards.

If you edit `skills/veriflow/` in a Veriflow checkout, re-run
`python install.py --project` to re-sync the committed copy at
`.claude/skills/veriflow/`. A test (`tests/test_install.py`) fails if the two
drift apart.

---

## Uninstall

```powershell
python install.py --project --uninstall --dry-run
python install.py --project --uninstall
```

This removes only the directory it installed, and refuses to remove one without
Veriflow's marker file. It also removes the parent `skills/` directory if it is
left empty, so a sibling skill is never affected. Restart Claude Code afterwards
so it stops offering the skill.

Nothing else needs undoing: the installer changed no setting outside that
directory.

---

## Using the scripts without Claude Code

Every script is a standalone CLI with `--help`:

```powershell
python skills\veriflow\scripts\run-checks.py --help
python skills\veriflow\scripts\run-security-tests.py --help
python skills\veriflow\scripts\run-api-tests.py --help
python skills\veriflow\scripts\run-openapi-tests.py --help
python skills\veriflow\scripts\run-browser-tests.py --help
```

Add `--json` to any of them for machine-readable output suitable for CI.

Exit codes are consistent: `0` means the executed checks passed, `1` means
something failed, `2` means a usage error, an unsafe target or an unknown
filter. A usage error is never reported as a pass.

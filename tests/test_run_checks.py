from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

# Load run-checks.py dynamically since the filename contains a hyphen
SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "skills"
    / "veriflow"
    / "scripts"
    / "run-checks.py"
).resolve()

spec = importlib.util.spec_from_file_location("run_checks_module", SCRIPT_PATH)
run_checks_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_checks_module)
discover_checks = run_checks_module.discover_checks
execute_check = run_checks_module.execute_check
run_checks = run_checks_module.run_checks
resolve_executable = run_checks_module.resolve_executable
diagnose_failure = run_checks_module.diagnose_failure


class TestRunChecksDiscovery(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_1_python_with_pytest_config(self):
        pyproject = self.root / "pyproject.toml"
        pyproject.write_text(
            "[project]\nname = 'sample'\n\n[tool.pytest.ini_options]\nminversion = '6.0'\n\n[tool.ruff]\nline-length = 88\n\n[tool.mypy]\nstrict = true\n",
            encoding="utf-8",
        )
        res = discover_checks(self.root)
        self.assertIn("python", res["detected_types"])
        check_names = {c["name"] for c in res["discovered_checks"]}
        self.assertIn("test", check_names)
        self.assertIn("lint", check_names)
        self.assertIn("typecheck", check_names)

        test_check = next(c for c in res["discovered_checks"] if c["name"] == "test")
        self.assertEqual(test_check["command"], ["pytest"])
        self.assertEqual(test_check["ecosystem"], "python")
        self.assertFalse(test_check["executed"])
        self.assertEqual(test_check["status"], "proposed")

    def test_2_python_without_recognizable_tests(self):
        (self.root / "setup.py").write_text("# setup script\n", encoding="utf-8")
        (self.root / "app.py").write_text("print('hello')\n", encoding="utf-8")

        res = discover_checks(self.root)
        self.assertIn("python", res["detected_types"])
        check_names = {c["name"] for c in res["discovered_checks"]}
        self.assertNotIn("test", check_names)
        self.assertTrue(
            any("No pytest configuration or test files discovered" in lim for lim in res["limitations"])
        )

    def test_3_javascript_multiple_package_scripts(self):
        package_json = self.root / "package.json"
        package_json.write_text(
            json.dumps({
                "scripts": {
                    "test": "jest",
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                    "check": "biome check .",
                    "build": "vite build",
                }
            }),
            encoding="utf-8",
        )
        res = discover_checks(self.root)
        check_names = [c["name"] for c in res["discovered_checks"]]
        self.assertIn("test", check_names)
        self.assertIn("lint", check_names)
        self.assertIn("typecheck", check_names)
        self.assertIn("check", check_names)
        self.assertIn("build", check_names)

    def test_4_package_manager_detection(self):
        # Case A: pnpm with lockfile
        (self.root / "package.json").write_text(
            json.dumps({"scripts": {"test": "vitest", "lint": "eslint ."}}),
            encoding="utf-8",
        )
        (self.root / "pnpm-lock.yaml").write_text("", encoding="utf-8")
        res_pnpm = discover_checks(self.root)
        self.assertEqual(res_pnpm["package_manager"], "pnpm")
        test_check = next(c for c in res_pnpm["discovered_checks"] if c["name"] == "test")
        lint_check = next(c for c in res_pnpm["discovered_checks"] if c["name"] == "lint")
        self.assertEqual(test_check["command"], ["pnpm", "test"])
        self.assertEqual(lint_check["command"], ["pnpm", "run", "lint"])

        # Case B: yarn declared in packageManager field without lockfile
        sub = self.root / "yarn_sub"
        sub.mkdir()
        (sub / "package.json").write_text(
            json.dumps({
                "packageManager": "yarn@4.1.0",
                "scripts": {"test": "jest"},
            }),
            encoding="utf-8",
        )
        res_yarn = discover_checks(sub)
        self.assertEqual(res_yarn["package_manager"], "yarn")
        sub_test = next(c for c in res_yarn["discovered_checks"] if c["name"] == "test")
        self.assertEqual(sub_test["command"], ["yarn", "test"])

    def test_5_malformed_package_json(self):
        (self.root / "package.json").write_text("{invalid json: broken", encoding="utf-8")
        # Must not raise an exception
        res = discover_checks(self.root)
        self.assertIsInstance(res, dict)
        self.assertEqual(res["discovered_checks"], [])
        self.assertTrue(
            any("No 'test' script found" in lim for lim in res["limitations"])
        )

    def test_6_missing_target_directory(self):
        nonexistent = self.root / "nonexistent_dir"
        with self.assertRaises(FileNotFoundError):
            discover_checks(nonexistent)

        # Also verify CLI exit code 1
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(nonexistent)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Error: project directory does not exist", proc.stderr)

    def test_7_empty_or_unsupported_project(self):
        res = discover_checks(self.root)
        self.assertEqual(res["discovered_checks"], [])
        self.assertFalse(res["executed"])
        self.assertTrue(
            any("No recognizable project configuration" in lim for lim in res["limitations"])
        )

    def test_8_discovery_does_not_execute_project_scripts(self):
        canary = self.root / "canary.txt"
        dangerous_script = f"python -c \"import pathlib; pathlib.Path(r'{canary}').touch()\""

        (self.root / "package.json").write_text(
            json.dumps({"scripts": {"test": dangerous_script}}),
            encoding="utf-8",
        )

        res = discover_checks(self.root)
        self.assertFalse(canary.exists(), "Discovery function must never execute scripts!")
        self.assertFalse(res["executed"])
        self.assertEqual(res["discovered_checks"][0]["executed"], False)
        self.assertEqual(res["discovered_checks"][0]["status"], "proposed")

        # Also test CLI execution preview
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(self.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertFalse(canary.exists(), "CLI discovery run must never execute scripts!")

    def test_9_commands_are_argument_lists(self):
        # Create a multi-language fixture
        (self.root / "package.json").write_text(
            json.dumps({"scripts": {"test": "npm test", "lint": "eslint ."}}),
            encoding="utf-8",
        )
        (self.root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        (self.root / "Cargo.toml").write_text("[package]\nname = 'test'\n", encoding="utf-8")

        res = discover_checks(self.root)
        self.assertGreaterEqual(len(res["discovered_checks"]), 3)
        for check in res["discovered_checks"]:
            cmd = check["command"]
            self.assertIsInstance(cmd, list, f"Command for {check['name']} must be a list")
            self.assertGreater(len(cmd), 0, f"Command list for {check['name']} must not be empty")
            for arg in cmd:
                self.assertIsInstance(arg, str, f"Command argument {arg} must be a string")

    def test_10_paths_containing_spaces(self):
        spaced_dir = self.root / "my target project with spaces"
        spaced_dir.mkdir()
        (spaced_dir / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\nminversion = '6.0'\n",
            encoding="utf-8",
        )

        res = discover_checks(spaced_dir)
        self.assertEqual(res["project_root"], str(spaced_dir.resolve()))
        self.assertEqual(res["discovered_checks"][0]["command"], ["pytest"])

        # CLI subprocess with space in argument
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(spaced_dir), "--json"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        parsed = json.loads(proc.stdout)
        self.assertEqual(parsed["project_root"], str(spaced_dir.resolve()))
        self.assertEqual(parsed["discovered_checks"][0]["command"], ["pytest"])

    def test_11_cli_help_and_exit_behavior(self):
        # --help flag
        proc_help = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc_help.returncode, 0)
        self.assertIn("Usage: run-checks.py", proc_help.stdout)

        # -h flag
        proc_h = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "-h"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc_h.returncode, 0)
        self.assertIn("Usage: run-checks.py", proc_h.stdout)

        # Valid project human-readable output
        proc_summary = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(self.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc_summary.returncode, 0)
        self.assertIn("Veriflow -- Check Discovery Preview", proc_summary.stdout)


class TestRunChecksExecution(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_execute_check_pass(self):
        check = {
            "name": "test",
            "ecosystem": "python",
            "command": [sys.executable, "-c", "import sys; sys.stdout.write('test-passed'); sys.exit(0)"],
            "reason": "Test runner simulation",
            "executed": False,
            "status": "proposed",
        }
        res = execute_check(check, self.root)
        self.assertTrue(res["executed"])
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["stdout"], "test-passed")
        self.assertEqual(res["stderr"], "")
        self.assertGreaterEqual(res["duration_seconds"], 0.0)
        self.assertIsNone(res["error_message"])

    def test_execute_check_fail(self):
        check = {
            "name": "lint",
            "ecosystem": "python",
            "command": [sys.executable, "-c", "import sys; sys.stderr.write('syntax error on line 1'); sys.exit(2)"],
            "reason": "Linter simulation",
            "executed": False,
            "status": "proposed",
        }
        res = execute_check(check, self.root)
        self.assertTrue(res["executed"])
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["exit_code"], 2)
        self.assertEqual(res["stderr"], "syntax error on line 1")
        self.assertIn("non-zero return code 2", res["error_message"])

    def test_execute_check_timeout(self):
        check = {
            "name": "long_task",
            "ecosystem": "python",
            "command": [sys.executable, "-c", "import time; time.sleep(10)"],
            "reason": "Timeout simulation",
            "executed": False,
            "status": "proposed",
        }
        res = execute_check(check, self.root, timeout=0.2)
        self.assertTrue(res["executed"])
        self.assertEqual(res["status"], "TIMEOUT")
        self.assertIsNone(res["exit_code"])
        self.assertIn("timed out after 0.2 seconds", res["error_message"])

    def test_execute_check_command_not_found(self):
        check = {
            "name": "missing_tool",
            "ecosystem": "custom",
            "command": ["nonexistent_binary_tool_xyz_987654", "--check"],
            "reason": "Missing binary simulation",
            "executed": False,
            "status": "proposed",
        }
        res = execute_check(check, self.root)
        self.assertTrue(res["executed"])
        self.assertEqual(res["status"], "COMMAND_NOT_FOUND")
        self.assertIsNone(res["exit_code"])
        self.assertIn("Executable not found", res["error_message"])

    def test_execute_check_invalid_command_error(self):
        check = {
            "name": "invalid",
            "ecosystem": "custom",
            "command": [],
            "reason": "Invalid command list",
            "executed": False,
            "status": "proposed",
        }
        res = execute_check(check, self.root)
        self.assertTrue(res["executed"])
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("Invalid command format", res["error_message"])

    def test_discover_checks_opt_in_execution_vs_preview(self):
        pyproject = self.root / "pyproject.toml"
        pyproject.write_text("[tool.pytest.ini_options]\nminversion = '6.0'\n", encoding="utf-8")

        # 1. Preview mode (execute=False, default)
        preview = discover_checks(self.root, execute=False)
        self.assertFalse(preview["executed"])
        self.assertEqual(preview["discovered_checks"][0]["status"], "proposed")
        self.assertFalse(preview["discovered_checks"][0]["executed"])
        self.assertEqual(preview["summary"]["passed"], 0)
        self.assertEqual(preview["summary"]["total"], 1)

        # 2. Opt-in execution mode (execute=True)
        executed = discover_checks(self.root, execute=True)
        self.assertTrue(executed["executed"])
        self.assertTrue(executed["discovered_checks"][0]["executed"])
        self.assertIn(executed["discovered_checks"][0]["status"], ("PASS", "FAIL", "COMMAND_NOT_FOUND"))
        self.assertIn("summary", executed)
        self.assertEqual(executed["summary"]["total"], 1)

    def test_cli_execute_flag_report(self):
        (self.root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        tests_dir = self.root / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_sample.py").write_text("def test_ok(): assert 1 == 1\n", encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(self.root), "--execute", "--json"],
            capture_output=True,
            text=True,
        )
        data = json.loads(proc.stdout)
        self.assertTrue(data["executed"])
        self.assertIn("summary", data)
        self.assertEqual(data["summary"]["total"], 1)

    def test_cli_execute_flag_failing_exit_code(self):
        (self.root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        tests_dir = self.root / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_bad.py").write_text("def test_fail(): assert False\n", encoding="utf-8")

        proc_exec = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(self.root), "--execute"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc_exec.returncode, 1)
        self.assertIn("Verification Check Execution Report", proc_exec.stdout)
        self.assertIn("[FAIL]", proc_exec.stdout)

        proc_preview = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(self.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc_preview.returncode, 0)
        self.assertIn("Check Discovery Preview", proc_preview.stdout)
        self.assertIn("proposed (executed: False)", proc_preview.stdout)

    def test_windows_batch_launcher_execution(self):
        if sys.platform != "win32":
            self.skipTest("Windows-only batch execution test")
        bat = self.root / "harmless_tool.bat"
        bat.write_text("@echo off\necho BATCH_OK: %1\nexit /b 0\n", encoding="utf-8")

        check = {
            "name": "batch_check",
            "ecosystem": "custom",
            "command": [str(bat), "test_arg"],
            "reason": "Harmless batch test",
            "executed": False,
            "status": "proposed",
        }
        res = execute_check(check, self.root)
        self.assertTrue(res["executed"])
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("BATCH_OK: test_arg", res["stdout"])

    def test_windows_cmd_launcher_execution_failure(self):
        if sys.platform != "win32":
            self.skipTest("Windows-only cmd execution test")
        cmd_file = self.root / "failing_tool.cmd"
        cmd_file.write_text("@echo off\necho CMD_FAILURE 1>&2\nexit /b 4\n", encoding="utf-8")

        check = {
            "name": "cmd_check",
            "ecosystem": "custom",
            "command": [str(cmd_file)],
            "reason": "Harmless failing cmd test",
            "executed": False,
            "status": "proposed",
        }
        res = execute_check(check, self.root)
        self.assertTrue(res["executed"])
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["exit_code"], 4)
        self.assertIn("CMD_FAILURE", res["stderr"])

    def test_windows_cwd_relative_batch_launcher_resolution(self):
        if sys.platform != "win32":
            self.skipTest("Windows-only launcher resolution test")
        bat = self.root / "runner.bat"
        bat.write_text("@echo off\necho RUNNER_CALLED\nexit /b 0\n", encoding="utf-8")

        check = {
            "name": "local_runner",
            "ecosystem": "custom",
            "command": ["runner.bat"],
            "reason": "Local launcher test",
            "executed": False,
            "status": "proposed",
        }
        res = execute_check(check, self.root)
        self.assertTrue(res["executed"])
        self.assertEqual(res["status"], "PASS")
        self.assertIn("RUNNER_CALLED", res["stdout"])



if __name__ == '__main__':
    unittest.main()

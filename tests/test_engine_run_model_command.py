"""Test engine/run_model_command.py, the argument-array adapter runner.

The runner replaces `eval "$MODEL_CALL_COMMAND"` in the adorno and havel
workflows. The adapter script lives in the caller workspace, which is the
runner's working directory.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parent.parent / "engine" / "run_model_command.py"
ADAPTER_SOURCE = """import os, sys
sys.stdout.write("reply for " + open(os.environ["CASE_TEXT_FILE"]).read())
sys.stdout.write(" key=" + os.environ.get("MODEL_API_KEY", "absent"))
sys.stdout.write(" other=" + os.environ.get("UNRELATED_VARIABLE", "absent"))
"""
FAILING_SOURCE = """import sys
sys.stderr.write("token=abc123 failed\\x07\\n")
raise SystemExit(4)
"""


class RunModelCommandTest(unittest.TestCase):
    """The runner accepts one Python script and forwards a fixed environment."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        (self.workspace / "adapter").mkdir()
        (self.workspace / "adapter" / "call.py").write_text(ADAPTER_SOURCE, encoding="utf-8")
        (self.workspace / "adapter" / "fail.py").write_text(FAILING_SOURCE, encoding="utf-8")
        (self.workspace / "case.txt").write_text("case", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_runner(self, command: str):
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "MODEL_CALL_COMMAND": command,
            "CASE_TEXT_FILE": str(self.workspace / "case.txt"),
            "MODEL_API_KEY": "synthetic",
            "UNRELATED_VARIABLE": "leak",
        }
        if "SystemRoot" in os.environ:
            environment["SystemRoot"] = os.environ["SystemRoot"]
        return subprocess.run([sys.executable, str(RUNNER)], cwd=self.workspace,
                              env=environment, capture_output=True, text=True, check=False)

    def test_valid_command_forwards_only_listed_variables(self):
        result = self.run_runner("python adapter/call.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "reply for case key=synthetic other=absent")

    def test_shell_syntax_is_rejected(self):
        for command in ("python adapter/call.py; echo x", "python adapter/call.py | cat",
                        "python $(echo adapter/call.py)", "python adapter/call.py > out"):
            with self.subTest(command=command):
                result = self.run_runner(command)
                self.assertEqual(result.returncode, 2)
                self.assertIn("shell syntax", result.stderr)

    def test_non_python_launcher_is_rejected(self):
        result = self.run_runner("bash adapter/call.py")
        self.assertEqual(result.returncode, 2)
        self.assertIn("one Python script", result.stderr)

    def test_script_outside_workspace_is_rejected(self):
        result = self.run_runner("python ../outside.py")
        self.assertEqual(result.returncode, 2)
        self.assertIn("remain in the workspace", result.stderr)

    def test_absolute_script_is_rejected(self):
        result = self.run_runner(f"python {self.workspace / 'adapter' / 'call.py'}")
        self.assertEqual(result.returncode, 2)
        self.assertIn("relative", result.stderr)

    def test_backslash_path_is_rejected_before_splitting(self):
        # POSIX shlex splitting drops backslashes. The check must see the raw text.
        result = self.run_runner("python adapter\\call.py")
        self.assertEqual(result.returncode, 2)
        self.assertIn("workspace-relative", result.stderr)

    def test_drive_qualified_path_is_rejected(self):
        result = self.run_runner("python C:adapter/call.py")
        self.assertEqual(result.returncode, 2)
        self.assertIn("relative", result.stderr)

    def test_failure_diagnostics_are_redacted_and_bounded(self):
        result = self.run_runner("python adapter/fail.py")
        self.assertEqual(result.returncode, 4)
        self.assertIn("token=<redacted>", result.stderr)
        self.assertNotIn("abc123", result.stderr)
        self.assertNotIn("\x07", result.stderr)


if __name__ == "__main__":
    unittest.main()

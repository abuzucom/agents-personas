"""Test engine/run_review.py end to end with a scripted adapter.

The adapter is a real script in the caller workspace. engine/run_model_command.py
runs it as an argument array. Only the model reply is scripted.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
CAPACITY_EXIT_CODE = 3
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
}
# The adapter pops one scripted step per call. A step is a reply string or an
# exit code. It appends each system prompt to prompts.log for inspection.
ADAPTER_SOURCE = """import json, os, sys
from pathlib import Path
here = Path(__file__).resolve().parent
steps = json.loads((here / "steps.json").read_text())
count_file = here / "count.txt"
index = int(count_file.read_text()) if count_file.exists() else 0
count_file.write_text(str(index + 1))
with open(here / "prompts.log", "a") as log:
    log.write(Path(os.environ["AUDIT_PROMPT_FILE"]).read_text() + "\\n=====\\n")
step = steps[index]
if isinstance(step, int):
    raise SystemExit(step)
if os.environ.get("USAGE_FILE"):
    Path(os.environ["USAGE_FILE"]).write_text(json.dumps({"input_tokens": 100, "output_tokens": 20}))
sys.stdout.write(step)
"""


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_review = _load("run_review")


def _reply(verdict: str, findings=None, mode: str = "PR") -> str:
    payload = {"mode": mode, "verdict": verdict, "findings": findings or []}
    return f"Mode: PR\nScope: one file.\nVERDICT: {verdict}\nVERDICT_JSON: {json.dumps(payload)}\n"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env=GIT_ENV).stdout.strip()


class RunReviewTest(unittest.TestCase):
    """run_mode reviews every chunk, validates, retries once, and combines."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base_dir = Path(self.temp.name)
        self.root = base_dir / "personas"
        persona_dir = self.root / "reviewers" / "euler"
        persona_dir.mkdir(parents=True)
        (persona_dir / "Q.md").write_text("Review code quality.\n", encoding="ascii")
        manifest = {"persona": "euler", "function": "quality", "modes": {"quality": {
            "prompt": "Q.md", "review": True, "default": True, "json_mode": "PR"}}}
        (persona_dir / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.repo = base_dir / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "maintenance.auto", "false")
        (self.repo / "keep.txt").write_text("base\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "base")
        self.base = _git(self.repo, "rev-parse", "HEAD")
        (self.repo / "app.py").write_text("value = 1\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "head")
        self.head = _git(self.repo, "rev-parse", "HEAD")
        self.adapter_dir = self.repo / "adapter"
        self.adapter_dir.mkdir()
        (self.adapter_dir / "fake.py").write_text(ADAPTER_SOURCE, encoding="utf-8")
        self.out = base_dir / "out"

    def tearDown(self):
        self.temp.cleanup()

    def script(self, *steps) -> None:
        (self.adapter_dir / "steps.json").write_text(json.dumps(list(steps)), encoding="utf-8")

    def options(self, **changes):
        values = {"root": self.root, "persona": "euler", "mode": "quality", "repo": self.repo,
                  "base": self.base, "head": self.head, "pr_number": 3, "out_dir": self.out,
                  "title": "Title", "body": "Body", "requested_caps": {},
                  "model_call_command": "python adapter/fake.py"}
        values.update(changes)
        return run_review.RunOptions(**values)

    def prompts(self) -> list[str]:
        return (self.adapter_dir / "prompts.log").read_text().split("\n=====\n")[:-1]

    def test_approve_reply_produces_result_file(self):
        self.script(_reply("APPROVE"))
        result = run_review.run_mode(self.options())
        stored = json.loads((self.out / "result.json").read_text(encoding="utf-8"))
        self.assertEqual((result["verdict"], stored["verdict"]), ("APPROVE", "APPROVE"))
        self.assertEqual((stored["persona"], stored["mode"], stored["head_sha"]),
                         ("euler", "quality", self.head))
        self.assertEqual(stored["chunks"], 1)

    def test_block_reply_collects_findings(self):
        finding = {"file": "app.py", "line": 1, "severity": "HIGH", "title": "t"}
        # A BLOCK gets one confirmation run. The active human approved this second reply.
        self.script(_reply("BLOCK", [finding]), _reply("BLOCK", [finding]))
        result = run_review.run_mode(self.options())
        self.assertEqual((result["verdict"], result["findings"]), ("BLOCK", [finding]))

    def test_system_prompt_carries_fence_rule(self):
        self.script(_reply("APPROVE"))
        run_review.run_mode(self.options())
        self.assertIn("REVIEW_TARGET", self.prompts()[0])
        self.assertIn("Review code quality.", self.prompts()[0])

    def test_invalid_reply_gets_one_retry_with_note(self):
        self.script("no verdict here", _reply("APPROVE"))
        result = run_review.run_mode(self.options())
        self.assertEqual(result["verdict"], "APPROVE")
        prompts = self.prompts()
        self.assertEqual(len(prompts), 2)
        self.assertIn("failed validation", prompts[1])

    def test_two_invalid_replies_fail_the_run(self):
        self.script("no verdict", "still no verdict")
        with self.assertRaisesRegex(run_review.ReviewError, "invalid response after one retry"):
            run_review.run_mode(self.options())
        self.assertFalse((self.out / "result.json").exists())

    def test_wrong_json_mode_counts_as_invalid(self):
        self.script(_reply("APPROVE", mode="other"), _reply("APPROVE", mode="other"))
        with self.assertRaises(run_review.ReviewError):
            run_review.run_mode(self.options())

    def test_capacity_exit_records_needs_human(self):
        self.script(CAPACITY_EXIT_CODE)
        result = run_review.run_mode(self.options())
        self.assertEqual(result["verdict"], "NEEDS-HUMAN")
        self.assertTrue(any("capacity" in reason for reason in result["reasons"]))

    def test_adapter_failure_fails_the_run(self):
        self.script(1)
        with self.assertRaisesRegex(run_review.ReviewError, "model command failed"):
            run_review.run_mode(self.options())

    def test_usage_is_summed(self):
        self.script(_reply("APPROVE"))
        usage = run_review.run_mode(self.options())["usage"]
        self.assertEqual(usage, {"input_tokens": 100, "output_tokens": 20})

    def test_unreviewed_binary_turns_approve_into_needs_human(self):
        (self.repo / "image.bin").write_bytes(bytes(range(256)))
        _git(self.repo, "add", "image.bin")
        _git(self.repo, "commit", "-q", "-m", "binary")
        self.script(_reply("APPROVE"))
        result = run_review.run_mode(self.options(head=_git(self.repo, "rev-parse", "HEAD")))
        self.assertEqual(result["verdict"], "NEEDS-HUMAN")
        self.assertIn("image.bin", result["unreviewed"])

    def test_cli_exits_nonzero_without_a_verdict(self):
        self.script("no verdict", "no verdict")
        command = [sys.executable, str(ENGINE_DIR / "run_review.py"), "--root", str(self.root),
                   "--persona", "euler", "--mode", "quality", "--repo", str(self.repo),
                   "--base", self.base, "--head", self.head, "--pr-number", "3",
                   "--out-dir", str(self.out)]
        environment = {**os.environ, "MODEL_CALL_COMMAND": "python adapter/fake.py"}
        completed = subprocess.run(command, capture_output=True, text=True, check=False, env=environment)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("invalid response", completed.stderr)


if __name__ == "__main__":
    unittest.main()

"""Test reviewers/havel/review_hooks.py through engine/run_review.py end to end.

The runs use the committed havel persona, a real git repository, and a
scripted adapter. They cover the trusted regimes option, the review prompt,
and the section 6 disclaimer rule.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "engine"
PERSONA_DIR = REPO_ROOT / "reviewers" / "havel"
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}
ADAPTER_SOURCE = """import json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
steps = json.loads((here / "steps.json").read_text())
count_file = here / "count.txt"
index = int(count_file.read_text()) if count_file.exists() else 0
count_file.write_text(str(index + 1))
sys.stdout.write(steps[index])
"""
DISCLAIMER = "NOT LEGAL ADVICE: engineering findings from a static review. Confirm with counsel."
COVERAGE = "**Mode:** PR\nScope: app.py.\nUnseen: callers.\n"
SOURCE = "def greet(name):\n    return name\n"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_review = _load("run_review")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=GIT_ENV
    ).stdout.strip()


def _reply(verdict: str, disclaimer: bool = True) -> str:
    payload = {"mode": "PR", "regimes": ["gdpr"], "regime_source": "declared", "verdict": verdict, "findings": []}
    notice = f"{DISCLAIMER}\n" if disclaimer else ""
    return (
        f"{COVERAGE}No findings.\n{notice}VERDICT: {verdict} - no personal data\nVERDICT_JSON: {json.dumps(payload)}\n"
    )


class EngineRunTest(unittest.TestCase):
    """engine/run_review.py runs the committed havel persona end to end."""

    def setUp(self):
        # Hosts without bubblewrap fall back to the plain child. CI sets 1 and keeps the sandbox required.
        if "PERSONAS_REQUIRE_SANDBOX" not in os.environ:
            os.environ["PERSONAS_REQUIRE_SANDBOX"] = "0"
            self.addCleanup(os.environ.pop, "PERSONAS_REQUIRE_SANDBOX", None)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base_dir = Path(self.temp.name)
        self.repo = base_dir / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "maintenance.auto", "false")
        (self.repo / "keep.txt").write_text("base\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "base")
        self.base = _git(self.repo, "rev-parse", "HEAD")
        (self.repo / "app.py").write_text(SOURCE, encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "head")
        self.head = _git(self.repo, "rev-parse", "HEAD")
        self.adapter_dir = self.repo / "adapter"
        self.adapter_dir.mkdir()
        (self.adapter_dir / "fake.py").write_text(ADAPTER_SOURCE, encoding="utf-8")
        self.out = base_dir / "out"

    def options(self, **changes):
        values = {
            "root": REPO_ROOT,
            "persona": "havel",
            "mode": "privacy",
            "repo": self.repo,
            "base": self.base,
            "head": self.head,
            "pr_number": 5,
            "out_dir": self.out,
            "title": "Title",
            "body": "DECLARED_SCOPE: us-ut",
            "requested_caps": {},
            "model_call_command": "python adapter/fake.py",
            "persona_options": json.dumps({"regimes": "eu"}),
        }
        values.update(changes)
        return run_review.RunOptions(**values)

    def run_steps(self, *steps: str) -> dict:
        (self.adapter_dir / "steps.json").write_text(json.dumps(list(steps)), encoding="utf-8")
        run_review.run_mode(self.options(stage="build"))
        return run_review.run_mode(self.options(stage="review"))

    def sent(self) -> dict:
        return json.loads((self.out / "case" / "envelopes" / "001.json").read_text(encoding="utf-8"))

    def test_declared_scope_rides_trusted_context(self):
        run_review.run_mode(self.options(stage="build"))
        sent = self.sent()
        self.assertEqual(sent["TRUSTED_CONTEXT"]["options"], {"regimes": "eu"})
        self.assertNotIn("us-ut", json.dumps(sent["TRUSTED_CONTEXT"]))

    def test_reply_disclaimer_approves_bundle_prompt(self):
        result = self.run_steps(_reply("APPROVE"))
        self.assertEqual(result["verdict"], "APPROVE")
        prompt = (self.out / "case" / "envelopes" / "001.prompt.0.txt").read_text(encoding="utf-8")
        self.assertIn("# Havel audit bundle: all (full tier)", prompt)
        self.assertIn("TRUSTED_CONTEXT.options.regimes takes precedence", prompt)

    def test_reply_without_disclaimer_retried(self):
        result = self.run_steps(_reply("APPROVE", disclaimer=False), _reply("APPROVE"))
        self.assertEqual(result["verdict"], "APPROVE")
        self.assertEqual((self.adapter_dir / "count.txt").read_text(encoding="utf-8"), "2")

    def test_disclaimerless_replies_fail(self):
        with self.assertRaises(run_review.ReviewError):
            self.run_steps(_reply("APPROVE", disclaimer=False), _reply("APPROVE", disclaimer=False))


if __name__ == "__main__":
    unittest.main()

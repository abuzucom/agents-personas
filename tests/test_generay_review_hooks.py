"""Test reviewers/generay/review_hooks.py: the time prescan and the TIME.md reply rules.

The end-to-end tests run engine/run_review.py with the committed generay
persona against a real git repository and a scripted adapter.
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
PERSONA_DIR = REPO_ROOT / "reviewers" / "generay"
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
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
NAIVE_NOW = "from datetime import datetime\nstamp = datetime.now()\n"
COVERAGE = "**Mode:** PR\nScope: app.py.\nUnseen: callers.\n"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


persona_hooks = _load("persona_hooks")
run_review = _load("run_review")
hooks = persona_hooks.load_review_hooks(PERSONA_DIR)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env=GIT_ENV).stdout.strip()


def _patch(text: str) -> str:
    body = "".join(f"+{line}\n" for line in text.splitlines())
    return f"--- /dev/null\n+++ b/app.py\n@@ -0,0 +1,{len(text.splitlines())} @@\n{body}"


def _reply(verdict: str, prescan=(), findings=(), escalations=()) -> str:
    payload = {"schema_version": "1", "mode": "PR", "verdict": verdict, "findings": list(findings),
               "escalations": list(escalations), "prescan": list(prescan)}
    return f"{COVERAGE}Findings above.\nVERDICT: {verdict}\nVERDICT_JSON: {json.dumps(payload)}\n"


def _envelope(prescan_ids=(), unreviewed=()) -> dict:
    prescan = [{"id": item, "file": "app.py", "line": 2, "check": "C9.1"} for item in prescan_ids]
    return {"TRUSTED_CONTEXT": {"persona": "generay"},
            "REVIEW_TARGET": {"files": {"app.py": _patch("a\nb\n")}, "prescan": prescan,
                              "unreviewed": list(unreviewed)}}


def _finding(**changes) -> dict:
    check = hooks.CHECKS["C9.1"]
    finding = {"severity": "MEDIUM", "check": "C9.1", "method": check.method, "file": "app.py", "line": 2,
               "title": "naive now", "confidence": "certain"}
    finding.update(changes)
    return finding


class CaseContextTest(unittest.TestCase):
    """case_context runs the time checks over the extracted head tree."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tree = Path(self.temp.name)
        (self.tree / "app.py").write_text(NAIVE_NOW, encoding="utf-8")

    def test_added_naive_now_becomes_an_advisory_candidate(self):
        result = hooks.case_context(self.tree, ["app.py"], {"app.py": _patch(NAIVE_NOW)}, {"exclude_paths": ""})
        checks = {item["check"] for item in result["context"]["prescan"]}
        self.assertIn("C9.1", checks)
        self.assertTrue(all(item["blocking"] is False for item in result["context"]["prescan"]))
        self.assertEqual(result["unreviewed"], [])

    def test_excluded_path_carries_no_candidate(self):
        result = hooks.case_context(self.tree, ["app.py"], {"app.py": _patch(NAIVE_NOW)}, {"exclude_paths": "app.py"})
        self.assertEqual(result["context"]["prescan"], [])

    def test_generay_defines_no_forced_verdict(self):
        self.assertFalse(hasattr(hooks, "forced_verdict"))


class ValidateReplyTest(unittest.TestCase):
    """validate_reply applies the TIME.md and SYNC.md reply rules to the engine envelope."""

    def problems(self, reply: str, **envelope_changes) -> list[str]:
        return hooks.validate_reply({}, reply, _envelope(**envelope_changes))

    def test_resolved_prescan_and_valid_finding_pass(self):
        reply = _reply("APPROVE", [{"id": "P1", "status": "dismissed", "reason": "zone set upstream"}],
                       [_finding(severity="LOW")])
        self.assertEqual(self.problems(reply, prescan_ids=["P1"]), [])

    def test_unresolved_prescan_item_fails(self):
        self.assertIn("prescan item P1 lacks a resolution", self.problems(_reply("APPROVE"), prescan_ids=["P1"]))

    def test_unknown_check_fails(self):
        self.assertIn("unknown check C99.9", self.problems(_reply("APPROVE", findings=[_finding(check="C99.9")])))

    def test_wrong_method_fails(self):
        problems = self.problems(_reply("APPROVE", findings=[_finding(method="wrong")]))
        self.assertTrue(any("must carry method" in problem for problem in problems), problems)

    def test_finding_outside_the_changed_files_fails(self):
        problems = self.problems(_reply("APPROVE", findings=[_finding(file="other.py")]))
        self.assertIn("finding cites other.py outside the changed files", problems)

    def test_critical_finding_demands_block(self):
        problems = self.problems(_reply("APPROVE", findings=[_finding(severity="CRITICAL")]))
        self.assertIn("verdict APPROVE conflicts with the severity rule, expected BLOCK", problems)

    def test_unreviewed_files_forbid_approve(self):
        self.assertIn("unreviewed files forbid APPROVE", self.problems(_reply("APPROVE"), unreviewed=["big.bin"]))


class EngineRunTest(unittest.TestCase):
    """engine/run_review.py runs the committed generay persona end to end."""

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
        (self.repo / "app.py").write_text(NAIVE_NOW, encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "head")
        self.head = _git(self.repo, "rev-parse", "HEAD")
        self.adapter_dir = self.repo / "adapter"
        self.adapter_dir.mkdir()
        (self.adapter_dir / "fake.py").write_text(ADAPTER_SOURCE, encoding="utf-8")
        self.out = base_dir / "out"

    def options(self, **changes):
        values = {"root": REPO_ROOT, "persona": "generay", "mode": "time", "repo": self.repo,
                  "base": self.base, "head": self.head, "pr_number": 3, "out_dir": self.out,
                  "title": "Title", "body": "Body", "requested_caps": {},
                  "model_call_command": "python adapter/fake.py"}
        values.update(changes)
        return run_review.RunOptions(**values)

    def sent(self) -> dict:
        return json.loads((self.out / "case" / "envelopes" / "001.json").read_text(encoding="utf-8"))

    def test_prescan_rides_in_the_review_target(self):
        run_review.run_mode(self.options(stage="build"))
        sent = self.sent()
        self.assertTrue(sent["REVIEW_TARGET"]["prescan"])
        self.assertNotIn("prescan", json.dumps(sent["TRUSTED_CONTEXT"]))

    def test_valid_reply_approves_with_both_policies_in_the_prompt(self):
        run_review.run_mode(self.options(stage="build"))
        resolutions = [{"id": item["id"], "status": "dismissed", "reason": "zone set upstream"}
                       for item in self.sent()["REVIEW_TARGET"]["prescan"]]
        (self.adapter_dir / "steps.json").write_text(json.dumps([_reply("APPROVE", resolutions)]), encoding="utf-8")
        result = run_review.run_mode(self.options(stage="review"))
        self.assertEqual(result["verdict"], "APPROVE")
        prompt = (self.out / "case" / "envelopes" / "001.prompt.0.txt").read_text(encoding="utf-8")
        self.assertLess(prompt.index("# TIME.md"), prompt.index("# SYNC.md"))


if __name__ == "__main__":
    unittest.main()

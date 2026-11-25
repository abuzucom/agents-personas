"""Test reviewers/euler/review_hooks.py: the prescan, the reply rules, and prescan BLOCK.

The end-to-end tests run engine/run_review.py with the committed euler
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
EMPTY_CATCH = "try:\n    run()\nexcept ValueError:\n    pass\n"
MUTABLE_DEFAULT = "def build(items=[]):\n    return items\n"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


persona_hooks = _load("persona_hooks")
envelope = _load("envelope")
run_review = _load("run_review")
hooks = persona_hooks.load_review_hooks(REPO_ROOT / "reviewers" / "euler")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=GIT_ENV
    ).stdout.strip()


def _patch(text: str) -> str:
    body = "".join(f"+{line}\n" for line in text.splitlines())
    return f"--- /dev/null\n+++ b/x\n@@ -0,0 +1,{len(text.splitlines())} @@\n{body}"


def _reply(verdict: str, prescan=(), findings=()) -> str:
    payload = {
        "schema_version": "1",
        "mode": "PR",
        "verdict": verdict,
        "findings": list(findings),
        "prescan": list(prescan),
    }
    # The euler quality mode requires the coverage lines. The active human approved this opening.
    return (
        f"Mode: PR\nScope: app.py.\nUnseen: callers.\nFindings above.\n\nVERDICT: {verdict} - summary\n"
        f"VERDICT_JSON: {json.dumps(payload)}\n"
    )


class TrustedContextTest(unittest.TestCase):
    """The prescan keeps candidates on added lines of changed, non-excluded files."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tree = Path(self.temp.name)
        (self.tree / "src").mkdir()
        (self.tree / "src" / "app.py").write_text(EMPTY_CATCH, encoding="utf-8")
        (self.tree / "src" / "util.py").write_text(MUTABLE_DEFAULT, encoding="utf-8")

    def context(self, patches: dict, exclude: str = "") -> dict:
        return hooks.case_context(self.tree, sorted(patches), patches, {"exclude_paths": exclude})

    def test_blocking_candidate_added_line(self):
        result = self.context({"src/app.py": _patch(EMPTY_CATCH)})
        classes = {item["class"] for item in result["context"]["prescan"]}
        self.assertIn("M1", classes)
        blocking = [item for item in result["context"]["prescan"] if item["class"] == "M1"]
        self.assertTrue(blocking[0]["blocking"])
        self.assertEqual(result["unreviewed"], [])

    def test_exclude_paths_drops_matching_files(self):
        result = self.context(
            {"src/app.py": _patch(EMPTY_CATCH), "src/util.py": _patch(MUTABLE_DEFAULT)}, exclude="src/app.py"
        )
        files = {item["file"] for item in result["context"]["prescan"]}
        self.assertNotIn("src/app.py", files)
        self.assertIn("src/util.py", files)

    def test_unchanged_lines_are_dropped(self):
        patch = "--- a/x\n+++ b/x\n@@ -1,4 +1,5 @@\n try:\n     run()\n except ValueError:\n     pass\n+value = 1\n"
        result = self.context({"src/app.py": patch})
        self.assertNotIn("M1", {item["class"] for item in result["context"]["prescan"]})

    def test_result_passes_engine_shape_check(self):
        patches = {"src/app.py": _patch(EMPTY_CATCH)}
        result = self.context(patches)
        self.assertIs(persona_hooks.check_context_result(result, sorted(patches)), result)


class ReplyHookTest(unittest.TestCase):
    """validate_reply applies QUALITY.md to an engine envelope."""

    def sent(self, prescan=(), unreviewed=()) -> dict:
        metadata = {"chunk": "1/1", "changed_file_count": 1, "unreviewed_count": len(unreviewed)}
        return json.loads(
            envelope.build_envelope(
                "euler",
                "quality",
                {"app.py": "+x\n"},
                "T",
                "B",
                metadata,
                context={"prescan": list(prescan)},
                changed_files=["app.py"],
                unreviewed=list(unreviewed),
            )
        )

    def test_resolved_prescan_passes(self):
        sent = self.sent([{"id": "P1", "file": "app.py", "line": 1}])
        reply = _reply("APPROVE", [{"id": "P1", "status": "dismissed", "reason": "clear"}])
        self.assertEqual(hooks.validate_reply({}, reply, sent), [])

    def test_unresolved_prescan_item_problem(self):
        sent = self.sent([{"id": "P1", "file": "app.py", "line": 1}])
        self.assertIn("prescan item P1 lacks a resolution", hooks.validate_reply({}, _reply("APPROVE"), sent))

    def test_unreviewed_files_forbid_approve(self):
        problems = hooks.validate_reply({}, _reply("APPROVE"), self.sent(unreviewed=["big.bin"]))
        self.assertIn("unreviewed files forbid APPROVE", problems)

    def test_finding_outside_chunk_files_problem(self):
        finding = {
            "severity": "LOW",
            "class": "Q13",
            "file": "other.py",
            "line": 2,
            "title": "t",
            "confidence": "certain",
        }
        problems = hooks.validate_reply({}, _reply("APPROVE", findings=[finding]), self.sent())
        self.assertIn("finding cites other.py outside the changed files", problems)


class ForcedVerdictTest(unittest.TestCase):
    """A blocking prescan candidate forces BLOCK. The reason names classes only."""

    def test_blocking_candidate_forces_block(self):
        forced = hooks.forced_verdict({
            "prescan": [
                {"file": "a/b.py", "class": "M1", "blocking": True},
                {"file": "c.py", "class": "Q13", "blocking": False},
            ]
        })
        self.assertEqual(forced, ("BLOCK", "blocking prescan finding in class M1"))

    def test_no_blocking_candidate_forces_nothing(self):
        self.assertIsNone(hooks.forced_verdict({"prescan": [{"file": "c.py", "class": "Q13", "blocking": False}]}))
        self.assertIsNone(hooks.forced_verdict({}))


class EngineRunTest(unittest.TestCase):
    """engine/run_review.py runs the committed euler persona end to end."""

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
        (self.repo / "app.py").write_text(EMPTY_CATCH, encoding="utf-8")
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
            "persona": "euler",
            "mode": "quality",
            "repo": self.repo,
            "base": self.base,
            "head": self.head,
            "pr_number": 3,
            "out_dir": self.out,
            "title": "Title",
            "body": "Body",
            "requested_caps": {},
            "model_call_command": "python adapter/fake.py",
        }
        values.update(changes)
        return run_review.RunOptions(**values)

    def prescan_ids(self) -> list[str]:
        sent = json.loads((self.out / "case" / "envelopes" / "001.json").read_text(encoding="utf-8"))
        return [item["id"] for item in sent["REVIEW_TARGET"]["prescan"]]

    def test_blocking_prescan_forces_block(self):
        run_review.run_mode(self.options(stage="build"))
        resolutions = [{"id": item, "status": "dismissed", "reason": "checked"} for item in self.prescan_ids()]
        (self.adapter_dir / "steps.json").write_text(json.dumps([_reply("APPROVE", resolutions)]), encoding="utf-8")
        result = run_review.run_mode(self.options(stage="review"))
        self.assertEqual(result["verdict"], "BLOCK")
        self.assertIn("blocking prescan finding in class M1", result["reasons"])

    def test_excluded_file_carries_no_prescan(self):
        run_review.run_mode(self.options(stage="build", persona_options='{"exclude_paths": "app.py"}'))
        self.assertEqual(self.prescan_ids(), [])


if __name__ == "__main__":
    unittest.main()

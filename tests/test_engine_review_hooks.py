"""Test persona review hooks: head extraction, trusted context, reply checks, forced verdicts.

A persona ships reviewers/<name>/review_hooks.py. The tests write a real hook
file into a temporary persona and run the engine stages against a real git
repository with a scripted adapter.
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
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
}
ADAPTER_SOURCE = """import json, os, sys
from pathlib import Path
here = Path(__file__).resolve().parent
steps = json.loads((here / "steps.json").read_text())
count_file = here / "count.txt"
index = int(count_file.read_text()) if count_file.exists() else 0
count_file.write_text(str(index + 1))
(here / f"case-{index}.json").write_text(Path(os.environ["CASE_TEXT_FILE"]).read_text())
sys.stdout.write(steps[index])
"""
# The hook records what it saw, flags every changed .py file, and marks
# file1.py unreviewed. A reply passes validate_reply only when it resolves
# every flagged item. A blocking item forces BLOCK.
HOOKS_SOURCE = """import json
from pathlib import Path


def case_context(head_dir, changed, patches, options):
    seen = sorted(path.relative_to(head_dir).as_posix() for path in Path(head_dir).rglob("*") if path.is_file())
    Path(options["record"]).write_text(json.dumps({"seen": seen, "changed": changed,
                                                   "patched": sorted(patches), "options": options}))
    python_files = [path for path in sorted(changed) if path.endswith(".py")]
    items = [{"id": f"P{index}", "file": path, "line": 1, "blocking": path == options["blocking"]}
             for index, path in enumerate(python_files, 1)]
    return {"context": {"prescan": items}, "unreviewed": ["file1.py"]}


def validate_reply(payload, response, envelope):
    wanted = {item["id"] for item in envelope["REVIEW_TARGET"]["prescan"]}
    resolved = {item.get("id") for item in payload.get("prescan", [])}
    return [f"prescan item {item} lacks a resolution" for item in sorted(wanted - resolved)]


def forced_verdict(context):
    blocking = [item["id"] for item in context.get("prescan", []) if item["blocking"]]
    return ("BLOCK", f"blocking prescan items {blocking}") if blocking else None
"""


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


envelope = _load("envelope")
builder = _load("build_pr_case")
persona_hooks = _load("persona_hooks")
run_review = _load("run_review")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env=GIT_ENV).stdout.strip()


def _reply(verdict: str, prescan_ids=()) -> str:
    payload = {"mode": "PR", "verdict": verdict, "findings": [],
               "prescan": [{"id": item, "status": "dismissed", "reason": "fine"} for item in prescan_ids]}
    return f"Mode: PR\nScope: the diff.\nVERDICT: {verdict}\nVERDICT_JSON: {json.dumps(payload)}\n"


class HookFixture(unittest.TestCase):
    """A persona with review hooks and a repository whose head adds three files."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base_dir = Path(self.temp.name)
        self.root = base_dir / "personas"
        self.persona_dir = self.root / "reviewers" / "euler"
        self.persona_dir.mkdir(parents=True)
        (self.persona_dir / "Q.md").write_text("Review code quality.\n", encoding="ascii")
        (self.persona_dir / "review_hooks.py").write_text(HOOKS_SOURCE, encoding="utf-8")
        self.record = base_dir / "record.json"
        manifest = {"persona": "euler", "function": "quality",
                    "options": {"record": {"type": "string", "default": str(self.record)},
                                "blocking": {"type": "string", "default": ""}},
                    "modes": {"quality": {"prompt": "Q.md", "review": True, "default": True, "json_mode": "PR"}}}
        (self.persona_dir / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.repo = base_dir / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "maintenance.auto", "false")
        (self.repo / "keep.txt").write_text("base\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "base")
        self.base = _git(self.repo, "rev-parse", "HEAD")
        (self.repo / "pkg").mkdir()
        (self.repo / "pkg" / "file0.py").write_text("value = 0\n", encoding="utf-8")
        (self.repo / "file1.py").write_text("value = 1\n", encoding="utf-8")
        (self.repo / "notes.md").write_text("notes\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "head")
        self.head = _git(self.repo, "rev-parse", "HEAD")
        # The working tree differs from the head. Extraction must read objects.
        (self.repo / "file1.py").write_text("tampered = True\n", encoding="utf-8")
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

    def sent_envelopes(self) -> list[dict]:
        return [json.loads(path.read_text()) for path in sorted(self.adapter_dir.glob("case-*.json"))]


class HeadTreeTest(HookFixture):
    """The builder writes regular head files from git objects and nothing else."""

    def test_extract_head_writes_head_blobs_only(self):
        target = Path(self.temp.name) / "tree"
        target.mkdir()
        builder.extract_head(self.repo, self.head, target)
        written = sorted(str(path.relative_to(target).as_posix()) for path in target.rglob("*") if path.is_file())
        self.assertEqual(written, ["file1.py", "keep.txt", "notes.md", "pkg/file0.py"])
        self.assertEqual((target / "file1.py").read_text(encoding="utf-8"), "value = 1\n")

    def test_extract_head_skips_symlinks(self):
        link = self.repo / "link.py"
        try:
            link.symlink_to("file1.py")
        except OSError as error:
            self.skipTest(f"platform denied symlink creation: {error}")
        _git(self.repo, "add", "link.py")
        _git(self.repo, "commit", "-q", "-m", "link")
        head = _git(self.repo, "rev-parse", "HEAD")
        target = Path(self.temp.name) / "tree"
        target.mkdir()
        builder.extract_head(self.repo, head, target)
        self.assertFalse((target / "link.py").exists())


class HeadTreeLimitTest(HookFixture):
    """Extraction skips oversized blobs and stops at the tree budget."""

    def add_head_file(self, name: str, size: int) -> str:
        (self.repo / name).write_bytes(b"x" * size)
        _git(self.repo, "add", name)
        _git(self.repo, "commit", "-q", "-m", name)
        return _git(self.repo, "rev-parse", "HEAD")

    def tree_dir(self) -> Path:
        target = Path(self.temp.name) / "tree"
        target.mkdir()
        return target

    def test_blob_over_the_file_cap_is_skipped_and_reported(self):
        head = self.add_head_file("big.bin", 4096)
        target = self.tree_dir()
        skipped = builder.extract_head(self.repo, head, target, max_blob_bytes=1024)
        self.assertEqual(skipped, ["big.bin"])
        self.assertFalse((target / "big.bin").exists())
        self.assertTrue((target / "keep.txt").is_file())

    def test_tree_over_the_total_cap_raises(self):
        head = self.add_head_file("big.bin", 4096)
        with self.assertRaisesRegex(builder.HeadTreeTooLarge, "exceeds"):
            builder.extract_head(self.repo, head, self.tree_dir(), max_tree_bytes=2048)

    def test_small_read_batches_write_every_file(self):
        target = self.tree_dir()
        builder.extract_head(self.repo, self.head, target, batch_bytes=1)
        written = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
        self.assertEqual(written, ["file1.py", "keep.txt", "notes.md", "pkg/file0.py"])

    def test_oversized_changed_file_becomes_unreviewed(self):
        options = builder.BuildOptions(
            repo=self.repo, base=self.base, head=self.head, out_dir=self.out, persona="euler", mode="quality",
            title="T", body="B", pr_number=1, max_chunks=20, max_envelope_bytes=200_000,
            hooks=run_review.persona_hooks.load_review_hooks(self.persona_dir),
            persona_options={"record": str(self.record), "blocking": ""}, max_blob_bytes=4)
        result = builder.collect_case_context(options, ["file1.py", "notes.md", "pkg/file0.py"], {})
        self.assertEqual(sorted(set(result["unreviewed"])), ["file1.py", "notes.md", "pkg/file0.py"])
        seen = json.loads(self.record.read_text(encoding="utf-8"))["seen"]
        self.assertEqual(seen, [])

    def test_tree_over_budget_skips_the_hook_and_marks_every_change(self):
        options = builder.BuildOptions(
            repo=self.repo, base=self.base, head=self.head, out_dir=self.out, persona="euler", mode="quality",
            title="T", body="B", pr_number=1, max_chunks=20, max_envelope_bytes=200_000,
            hooks=run_review.persona_hooks.load_review_hooks(self.persona_dir),
            persona_options={"record": str(self.record), "blocking": ""}, max_tree_bytes=8)
        changed = ["file1.py", "notes.md", "pkg/file0.py"]
        result = builder.collect_case_context(options, changed, {})
        self.assertEqual(result, {"context": {}, "unreviewed": changed})
        self.assertFalse(self.record.exists())


class EnvelopeContextTest(unittest.TestCase):
    """Persona context joins the untrusted REVIEW_TARGET and its digest.

    Hook items can quote pull request text, so TRUSTED_CONTEXT never holds them.
    """

    def build(self, context):
        return json.loads(envelope.build_envelope("euler", "quality", {"a.py": "+x\n"}, "T", "B", {},
                                                  context=context))

    def test_context_keys_join_case_context_and_digest(self):
        with_item = self.build({"prescan": [{"id": "P1", "file": "a.py"}]})
        without = self.build({"prescan": []})
        self.assertEqual(with_item["REVIEW_TARGET"]["prescan"], [{"id": "P1", "file": "a.py"}])
        self.assertNotIn("prescan", with_item["TRUSTED_CONTEXT"])
        self.assertNotEqual(with_item["REVIEW_TARGET"]["sha256"], without["REVIEW_TARGET"]["sha256"])
        self.assertEqual(with_item["TRUSTED_CONTEXT"]["sha256"], without["TRUSTED_CONTEXT"]["sha256"])

    def test_reserved_key_is_rejected(self):
        for key in ("title", "body", "files", "note", "sha256"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "reserved"):
                self.build({key: []})


class HookResultTest(unittest.TestCase):
    """The engine checks the shape a hook returns before it trusts it."""

    def test_valid_result_passes(self):
        result = {"context": {"prescan": [{"file": "a.py"}]}, "unreviewed": ["b.py"]}
        self.assertEqual(persona_hooks.check_context_result(result, ["a.py", "b.py"]), result)

    def test_malformed_results_are_rejected(self):
        cases = {
            "not an object": [],
            "context must be an object": {"context": [], "unreviewed": []},
            "list of objects with a file": {"context": {"prescan": [{"line": 1}]}, "unreviewed": []},
            "outside the changed files": {"context": {"prescan": [{"file": "z.py"}]}, "unreviewed": []},
            "unreviewed must list changed files": {"context": {}, "unreviewed": ["z.py"]},
        }
        for message, result in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                persona_hooks.check_context_result(result, ["a.py"])

    def test_hook_file_must_be_regular(self):
        with tempfile.TemporaryDirectory() as directory:
            persona_dir = Path(directory)
            (persona_dir / "elsewhere.py").write_text(HOOKS_SOURCE, encoding="utf-8")
            try:
                (persona_dir / "review_hooks.py").symlink_to(persona_dir / "elsewhere.py")
            except OSError as error:
                self.skipTest(f"platform denied symlink creation: {error}")
            with self.assertRaisesRegex(ValueError, "regular file"):
                persona_hooks.load_review_hooks(persona_dir)

    def test_persona_without_hooks_loads_none(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(persona_hooks.load_review_hooks(Path(directory)))


class BuildStageTest(HookFixture):
    """The build stage runs case_context and calls no model."""

    def test_build_stage_writes_the_case_without_a_model_call(self):
        self.script()
        run_review.run_mode(self.options(stage="build", persona_options='{"blocking": ""}'))
        manifest = json.loads((self.out / "case" / "manifest.json").read_text(encoding="utf-8"))
        self.assertFalse((self.out / "result.json").exists())
        self.assertFalse((self.adapter_dir / "count.txt").exists())
        self.assertIn("file1.py", manifest["unreviewed"])
        record = json.loads(self.record.read_text(encoding="utf-8"))
        self.assertEqual(record["seen"], ["file1.py", "keep.txt", "notes.md", "pkg/file0.py"])
        self.assertEqual(record["options"]["blocking"], "")
        context = json.loads((self.out / "case" / "case_context.json").read_text(encoding="utf-8"))
        self.assertEqual([item["file"] for item in context["prescan"]], ["file1.py", "pkg/file0.py"])

    def test_each_chunk_carries_only_its_own_items(self):
        self.script()
        run_review.run_mode(self.options(stage="build", requested_caps={"max_envelope_bytes": 1500}))
        manifest = json.loads((self.out / "case" / "manifest.json").read_text(encoding="utf-8"))
        self.assertGreater(len(manifest["chunks"]), 1)
        for chunk in manifest["chunks"]:
            with self.subTest(chunk=chunk["envelope"]):
                body = json.loads((self.out / "case" / "envelopes" / chunk["envelope"]).read_text())
                files = {item["file"] for item in body["REVIEW_TARGET"]["prescan"]}
                self.assertTrue(files <= set(chunk["files"]))

    def test_undeclared_persona_option_fails_the_build(self):
        with self.assertRaisesRegex(run_review.reviewers.ReviewerError, "undeclared option"):
            run_review.run_mode(self.options(stage="build", persona_options='{"exclude": "x"}'))


class ReviewStageTest(HookFixture):
    """The review stage reuses the built case, applies validate_reply, and forced_verdict."""

    def test_review_stage_reuses_the_built_case(self):
        run_review.run_mode(self.options(stage="build"))
        (self.out / "case" / "envelopes" / "001.json").write_text(
            (self.out / "case" / "envelopes" / "001.json").read_text().replace("Title", "Built"))
        self.script(_reply("APPROVE", ("P1", "P2")))
        result = run_review.run_mode(self.options(stage="review"))
        self.assertIn("Built", json.dumps(self.sent_envelopes()[0]))
        self.assertEqual(result["verdict"], "NEEDS-HUMAN")

    def test_review_stage_without_a_built_case_fails(self):
        with self.assertRaisesRegex(run_review.ReviewError, "run the build stage first"):
            run_review.run_mode(self.options(stage="review"))

    def test_validate_reply_problem_triggers_one_retry(self):
        self.script(_reply("APPROVE"), _reply("APPROVE", ("P1", "P2")))
        result = run_review.run_mode(self.options())
        self.assertEqual(len(self.sent_envelopes()), 2)
        self.assertEqual(result["verdict"], "NEEDS-HUMAN")

    def test_validate_reply_problem_twice_fails_the_run(self):
        self.script(_reply("APPROVE"), _reply("APPROVE", ("P1",)))
        with self.assertRaisesRegex(run_review.ReviewError, "prescan item P2 lacks a resolution"):
            run_review.run_mode(self.options())

    def test_forced_verdict_overrides_a_milder_chunk_verdict(self):
        self.script(_reply("APPROVE", ("P1", "P2")))
        result = run_review.run_mode(self.options(persona_options='{"blocking": "pkg/file0.py"}'))
        self.assertEqual(result["verdict"], "BLOCK")
        self.assertIn("blocking prescan items ['P2']", result["reasons"])


if __name__ == "__main__":
    unittest.main()

"""Test multi-file prompts in the persona manifest.

A mode's prompt may name one file or a list of files. The engine validates
each path, then joins the files in list order for the review, the eval, and
context rendering. generay's time mode loads TIME.md and SYNC.md this way.
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests import test_engine_run_review as fixture

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reviewers = _load("reviewers")
render_context = _load("render_context")


class PromptListTest(unittest.TestCase):
    """reviewers.load_prompt joins every listed file in order."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.persona = Path(self.temp.name)
        (self.persona / "A.md").write_text("first rules\n", encoding="ascii")
        (self.persona / "B.md").write_text("second rules\n", encoding="ascii")

    def test_list_joins_in_order(self):
        text = reviewers.load_prompt(self.persona, ["A.md", "B.md"])
        self.assertEqual(text, "first rules\n" + reviewers.PROMPT_SEPARATOR + "second rules\n")

    def test_single_string_keeps_its_text(self):
        self.assertEqual(reviewers.load_prompt(self.persona, "A.md"), "first rules\n")

    def test_invalid_lists_are_refused(self):
        too_many = ["A.md"] * (reviewers.MAX_PROMPT_FILES + 1)
        for prompt in ([], ["A.md", 3], ["A.md", "../x.md"], ["A.md", "A.md"], too_many):
            with self.subTest(prompt=prompt):
                with self.assertRaises(reviewers.ReviewerError):
                    reviewers.prompt_paths(self.persona, prompt)


class ManifestPromptListTest(unittest.TestCase):
    """The manifest check accepts a prompt list and reports each missing file."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.persona = self.root / "reviewers" / "sample"
        self.persona.mkdir(parents=True)
        (self.persona / "A.md").write_bytes(b"a\n")
        (self.persona / "B.md").write_bytes(b"b\n")

    def write(self, prompt) -> None:
        manifest = {"persona": "sample", "function": "review", "modes": {
            "review": {"prompt": prompt, "review": True, "default": True},
            "notes": {"prompt": prompt, "context": True}}}
        (self.persona / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_prompt_list_validates(self):
        self.write(["A.md", "B.md"])
        self.assertEqual(reviewers.validate_persona(self.persona), [])

    def test_missing_listed_file_is_reported(self):
        self.write(["A.md", "C.md"])
        findings = reviewers.validate_persona(self.persona)
        self.assertTrue(any("prompt 'C.md' is missing" in finding for finding in findings), findings)

    def test_context_mode_renders_the_joined_files(self):
        self.write(["A.md", "B.md"])
        rendered = render_context.render_context(self.root, "sample", "notes")
        self.assertEqual(rendered, ("a\n" + reviewers.PROMPT_SEPARATOR + "b\n").encode("ascii"))


class EngineRunPromptListTest(unittest.TestCase):
    """run_review sends both files as the system prompt."""

    setUp = fixture.RunReviewTest.setUp
    tearDown = fixture.RunReviewTest.tearDown
    script = fixture.RunReviewTest.script
    options = fixture.RunReviewTest.options
    prompts = fixture.RunReviewTest.prompts

    def test_review_prompt_holds_both_files_in_order(self):
        persona = self.root / "reviewers" / "euler"
        (persona / "S.md").write_text("Sync rules.\n", encoding="ascii")
        manifest = json.loads((persona / "reviewer.json").read_text(encoding="utf-8"))
        manifest["modes"]["quality"]["prompt"] = ["Q.md", "S.md"]
        (persona / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.script(fixture._reply("APPROVE"))
        fixture.run_review.run_mode(self.options())
        prompt = self.prompts()[0]
        self.assertLess(prompt.index("Review code quality."), prompt.index("Sync rules."))


if __name__ == "__main__":
    unittest.main()

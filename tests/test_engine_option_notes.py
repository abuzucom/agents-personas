"""Test option notes: fixed scope notes keyed by a trusted option value.

A manifest may map a trusted string option's value to a fixed note. When the
caller value matches, the engine adds the note to the result, the check
summary, and the pull request comment. The manifest supplies every note.
No model output and no pull request text can add or change one.
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


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reviewers = _load("reviewers")
review_output = _load("review_output")
run_review = _load("run_review")

BASELINE_NOTE = "Scope: baseline. Regime-specific issues may exist that this run did not check."
OPTIONS = {
    "regimes": {"type": "string", "default": "undeclared", "trusted": True},
    "exclude_paths": {"type": "string", "default": ""},
}
NOTES = {"regimes": {"baseline": BASELINE_NOTE, "undeclared": "Scope: undeclared."}}
MANIFEST = {
    "persona": "sample",
    "function": "privacy",
    "options": OPTIONS,
    "option_notes": NOTES,
    "modes": {"privacy": {"prompt": "AUDIT.md", "review": True, "default": True}},
}
REPLY = (
    'Findings above.\nVERDICT: APPROVE - clean\nVERDICT_JSON: {"mode": "PR", "verdict": "APPROVE", "findings": []}\n'
)
ADAPTER_SOURCE = "import sys\nsys.stdout.write(open(sys.argv[0].replace('fake.py', 'reply.txt')).read())\n"
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


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=GIT_ENV)
    return result.stdout.strip()


def _findings(**changes) -> list:
    with tempfile.TemporaryDirectory() as directory:
        persona_dir = Path(directory) / "reviewers" / "sample"
        persona_dir.mkdir(parents=True)
        (persona_dir / "AUDIT.md").write_text("prompt\n", encoding="ascii")
        (persona_dir / "reviewer.json").write_text(json.dumps({**MANIFEST, **changes}), encoding="utf-8")
        return reviewers.validate_persona(persona_dir)


class ManifestTest(unittest.TestCase):
    """option_notes keys name trusted string options. Each note is printable ASCII."""

    def test_valid_notes_pass(self):
        self.assertEqual(_findings(), [])

    def test_note_untrusted_option_reported(self):
        problems = _findings(option_notes={"exclude_paths": {"": "x"}})
        self.assertIn("sample: option_notes 'exclude_paths' needs a trusted string option", problems)

    def test_note_undeclared_option_reported(self):
        self.assertIn(
            "sample: option_notes 'missing' needs a trusted string option", _findings(option_notes={"missing": {}})
        )

    def test_bad_note_text_is_reported(self):
        for note in ("", "line\nbreak", "x" * (reviewers.MAX_NOTE_CHARS + 1), 3):
            with self.subTest(note=note):
                problems = _findings(option_notes={"regimes": {"baseline": note}})
                self.assertIn(
                    f"sample: option_notes 'regimes' value 'baseline' needs printable ASCII text of 1 to "
                    f"{reviewers.MAX_NOTE_CHARS} characters",
                    problems,
                )

    def test_notes_follow_the_trusted_value(self):
        self.assertEqual(reviewers.option_notes(MANIFEST, {"regimes": "baseline"}), [BASELINE_NOTE])
        self.assertEqual(reviewers.option_notes(MANIFEST, {"regimes": " baseline "}), [BASELINE_NOTE])
        self.assertEqual(reviewers.option_notes(MANIFEST, {"regimes": "eu, us"}), [])
        self.assertEqual(reviewers.option_notes({**MANIFEST, "option_notes": {}}, {"regimes": "baseline"}), [])


class RenderTest(unittest.TestCase):
    """The summary and the comment carry each note."""

    def result(self, notes: list) -> dict:
        return {
            "persona": "sample",
            "mode": "privacy",
            "head_sha": "a" * 40,
            "verdict": "APPROVE",
            "chunks": 1,
            "reports": ["Clean."],
            "notes": notes,
        }

    def test_summary_lists_each_note(self):
        self.assertIn(f"Note: {BASELINE_NOTE}", review_output.summary(self.result([BASELINE_NOTE])))

    def test_comment_shows_note_before_reports(self):
        body = review_output.comment_body(self.result([BASELINE_NOTE]))
        self.assertIn(f"> **Note:** {BASELINE_NOTE}", body)
        self.assertLess(body.index(BASELINE_NOTE), body.index("### Chunk"))

    def test_result_without_notes_renders_before(self):
        result = self.result([])
        self.assertNotIn("Note:", review_output.summary(result))
        self.assertNotIn("Note:", review_output.comment_body(result))


class EngineRunTest(unittest.TestCase):
    """A full run records the note of the caller's trusted value in result.json."""

    def setUp(self):
        if "PERSONAS_REQUIRE_SANDBOX" not in os.environ:
            os.environ["PERSONAS_REQUIRE_SANDBOX"] = "0"
            self.addCleanup(os.environ.pop, "PERSONAS_REQUIRE_SANDBOX", None)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base_dir = Path(temp.name)
        self.root = base_dir / "root"
        persona_dir = self.root / "reviewers" / "sample"
        persona_dir.mkdir(parents=True)
        (persona_dir / "AUDIT.md").write_text("prompt\n", encoding="ascii")
        (persona_dir / "reviewer.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
        self.repo = base_dir / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "maintenance.auto", "false")
        (self.repo / "keep.txt").write_text("base\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "base")
        self.base = _git(self.repo, "rev-parse", "HEAD")
        (self.repo / "app.py").write_text("value = 1\n", encoding="utf-8")
        adapter = self.repo / "adapter"
        adapter.mkdir()
        (adapter / "fake.py").write_text(ADAPTER_SOURCE, encoding="utf-8")
        (adapter / "reply.txt").write_text(REPLY, encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "head")
        self.head = _git(self.repo, "rev-parse", "HEAD")
        self.out = base_dir / "out"

    def run_with(self, persona_options: str) -> dict:
        options = run_review.RunOptions(
            root=self.root,
            persona="sample",
            mode="privacy",
            repo=self.repo,
            base=self.base,
            head=self.head,
            pr_number=3,
            out_dir=self.out,
            title="Title",
            body="Body",
            requested_caps={},
            model_call_command="python adapter/fake.py",
            persona_options=persona_options,
        )
        return run_review.run_mode(options)

    def test_baseline_run_carries_the_note(self):
        result = self.run_with('{"regimes": "baseline"}')
        self.assertEqual(result["notes"], [BASELINE_NOTE])
        self.assertEqual(json.loads((self.out / "result.json").read_text(encoding="utf-8"))["notes"], [BASELINE_NOTE])

    def test_declared_run_carries_no_note(self):
        self.assertEqual(self.run_with('{"regimes": "eu, us"}')["notes"], [])


if __name__ == "__main__":
    unittest.main()

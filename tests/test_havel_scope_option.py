"""Test the havel scope option: validation, the scope notes, and the Unseen rule.

case_context checks the trusted regimes option against
docs/regimes/scope-profiles.md before any envelope exists. Only profile
names, slugs, the reserved word undeclared, and the empty value reach
TRUSTED_CONTEXT. A baseline, undeclared, or empty scope reviews the baseline
classes alone. The engine note tells maintainers that regime-specific issues
may exist that the run did not check. AUDIT.md has the report name those
unchecked obligations on its Unseen line.
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
PERSONA_DIR = REPO_ROOT / "reviewers" / "havel"
ENGINE_DIR = REPO_ROOT / "engine"
UNCHECKED_PHRASE = "Regime-specific issues may exist that this run did not check."
UNSEEN_RULE = (
    "Under a `baseline`, `undeclared`, or empty scope, name the unchecked regime-specific obligations "
    "on the `Unseen:` line of the report."
)
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


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hooks = _load("havel_scope_hooks", PERSONA_DIR / "review_hooks.py")
reviewers = _load("reviewers", ENGINE_DIR / "reviewers.py")
run_review = _load("run_review", ENGINE_DIR / "run_review.py")
MANIFEST = json.loads((PERSONA_DIR / "reviewer.json").read_text(encoding="utf-8"))


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=GIT_ENV)
    return result.stdout.strip()


class CaseContextTest(unittest.TestCase):
    """Known and empty scopes pass with no context. Unknown or blank names raise."""

    def context(self, regimes: str) -> dict:
        return hooks.case_context("/nonexistent", ["app.py"], {"app.py": "+x\n"}, {"regimes": regimes})

    def test_known_scopes_pass(self):
        for regimes in ("", "  ", "baseline", "undeclared", "all", "eu, us", "gdpr", "us-ca, pipeda"):
            with self.subTest(regimes=regimes):
                self.assertEqual(self.context(regimes), {"context": {}, "unreviewed": []})

    def test_unknown_name_is_refused(self):
        with self.assertRaisesRegex(ValueError, "scope 'mars' matches no profile and no slug"):
            self.context("eu, mars")

    def test_blank_entry_is_refused(self):
        for regimes in (", ,", "eu,", "eu,,us"):
            with self.subTest(regimes=regimes), self.assertRaisesRegex(ValueError, "regimes holds a blank entry"):
                self.context(regimes)


class ScopeNoteTest(unittest.TestCase):
    """A scope without regime deltas carries a note that names the unchecked issues."""

    def test_baseline_notes_name_unchecked(self):
        for regimes in ("baseline", "undeclared", ""):
            with self.subTest(regimes=regimes):
                notes = reviewers.option_notes(MANIFEST, {"regimes": regimes})
                self.assertEqual(len(notes), 1)
                self.assertIn(UNCHECKED_PHRASE, notes[0])

    def test_declared_scope_lacks_note(self):
        self.assertEqual(reviewers.option_notes(MANIFEST, {"regimes": "eu, us"}), [])

    def test_manifest_stays_valid(self):
        self.assertEqual(reviewers.validate_persona(PERSONA_DIR), [])


class UnseenRuleTest(unittest.TestCase):
    """AUDIT.md step 0b and the review bundle carry the Unseen rule."""

    def test_audit_carries_the_unseen_rule(self):
        self.assertIn(UNSEEN_RULE, (PERSONA_DIR / "AUDIT.md").read_text(encoding="utf-8"))

    def test_review_bundle_carries_unseen_rule(self):
        prompt = MANIFEST["modes"]["privacy"]["prompt"]
        self.assertIn(UNSEEN_RULE, (PERSONA_DIR / prompt).read_text(encoding="utf-8"))


class EngineBuildTest(unittest.TestCase):
    """A build stage for the committed havel persona applies the scope check."""

    def setUp(self):
        if "PERSONAS_REQUIRE_SANDBOX" not in os.environ:
            os.environ["PERSONAS_REQUIRE_SANDBOX"] = "0"
            self.addCleanup(os.environ.pop, "PERSONAS_REQUIRE_SANDBOX", None)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base_dir = Path(temp.name)
        self.repo = base_dir / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "maintenance.auto", "false")
        (self.repo / "keep.txt").write_text("base\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "base")
        self.base = _git(self.repo, "rev-parse", "HEAD")
        (self.repo / "app.py").write_text("email = user.email\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "head")
        self.head = _git(self.repo, "rev-parse", "HEAD")
        self.out = base_dir / "out"

    def build(self, persona_options: str):
        options = run_review.RunOptions(
            root=REPO_ROOT,
            persona="havel",
            mode="privacy",
            repo=self.repo,
            base=self.base,
            head=self.head,
            pr_number=3,
            out_dir=self.out,
            title="Title",
            body="Body",
            requested_caps={},
            stage="build",
            persona_options=persona_options,
        )
        return run_review.run_mode(options)

    def test_known_scope_reaches_trusted_context(self):
        self.build('{"regimes": "eu, us"}')
        sent = json.loads((self.out / "case" / "envelopes" / "001.json").read_text(encoding="utf-8"))
        self.assertEqual(sent["TRUSTED_CONTEXT"]["options"], {"regimes": "eu, us"})

    def test_unknown_scope_stops_the_build(self):
        with self.assertRaises(run_review.ReviewError):
            self.build('{"regimes": "mars"}')
        self.assertFalse((self.out / "case" / "envelopes").exists())


if __name__ == "__main__":
    unittest.main()

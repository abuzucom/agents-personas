"""Test trusted persona options.

A manifest option may set "trusted": true. The engine validates the caller
value as for any option. A trusted value joins TRUSTED_CONTEXT.options in
every envelope, and the trusted digest covers it. An untrusted value stays
out of the envelope. An envelope without trusted options keeps the old shape.
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
envelope = _load("envelope")
run_review = _load("run_review")

OPTIONS = {
    "regimes": {"type": "string", "default": "undeclared", "trusted": True},
    "exclude_paths": {"type": "string", "default": ""},
}
MANIFEST = {
    "persona": "sample",
    "function": "privacy",
    "options": OPTIONS,
    "modes": {"privacy": {"prompt": "AUDIT.md", "review": True, "default": True}},
}
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


def _persona_findings(options: object) -> list:
    with tempfile.TemporaryDirectory() as directory:
        persona_dir = Path(directory) / "reviewers" / "sample"
        persona_dir.mkdir(parents=True)
        (persona_dir / "AUDIT.md").write_text("prompt\n", encoding="ascii")
        (persona_dir / "reviewer.json").write_text(json.dumps({**MANIFEST, "options": options}), encoding="utf-8")
        return reviewers.validate_persona(persona_dir)


def _envelope(**changes) -> dict:
    values = {"options": None}
    values.update(changes)
    text = envelope.build_envelope("sample", "privacy", {"a.py": "+x\n"}, "T", "B", {"chunk": "1/1"}, **values)
    return json.loads(text)


class ManifestTest(unittest.TestCase):
    """The trusted flag is an optional boolean on an option."""

    def test_trusted_option_validates(self):
        self.assertEqual(_persona_findings(OPTIONS), [])

    def test_non_boolean_trusted_flag_reported(self):
        options = {"regimes": {"type": "string", "default": "", "trusted": "yes"}}
        self.assertIn("sample: option 'regimes': trusted must be true or false", _persona_findings(options))

    def test_trusted_values_hold_trusted_options(self):
        resolved = reviewers.resolve_options(MANIFEST, '{"regimes": "eu, us", "exclude_paths": "tests/**"}')
        self.assertEqual(reviewers.trusted_option_values(MANIFEST, resolved), {"regimes": "eu, us"})

    def test_trusted_value_fails_validation_refused(self):
        with self.assertRaisesRegex(reviewers.ReviewerError, "option 'regimes' must be a string"):
            reviewers.resolve_options(MANIFEST, '{"regimes": 3}')


class EnvelopeTest(unittest.TestCase):
    """Trusted values sit in TRUSTED_CONTEXT under the trusted digest."""

    def test_trusted_values_join_trusted_context(self):
        sent = _envelope(options={"regimes": "eu, us"})
        self.assertEqual(sent["TRUSTED_CONTEXT"]["options"], {"regimes": "eu, us"})
        self.assertNotIn("regimes", json.dumps(sent["REVIEW_TARGET"]))

    def test_trusted_digest_covers_the_values(self):
        first = _envelope(options={"regimes": "eu"})["TRUSTED_CONTEXT"]["sha256"]
        second = _envelope(options={"regimes": "us"})["TRUSTED_CONTEXT"]["sha256"]
        self.assertNotEqual(first, second)

    def test_plain_envelope_keeps_shape(self):
        old = json.loads(envelope.build_envelope("sample", "privacy", {"a.py": "+x\n"}, "T", "B", {"chunk": "1/1"}))
        for sent in (_envelope(), _envelope(options={})):
            with self.subTest(sent=sent):
                self.assertEqual(sent, old)
                self.assertNotIn("options", sent["TRUSTED_CONTEXT"])


class EngineRunTest(unittest.TestCase):
    """A build stage writes only the trusted values into every envelope."""

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
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "head")
        self.head = _git(self.repo, "rev-parse", "HEAD")
        self.out = base_dir / "out"

    def build(self, persona_options: str) -> dict:
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
            stage="build",
            persona_options=persona_options,
        )
        run_review.run_mode(options)
        return json.loads((self.out / "case" / "envelopes" / "001.json").read_text(encoding="utf-8"))

    def test_build_writes_caller_option(self):
        sent = self.build('{"regimes": "eu, us", "exclude_paths": "tests/**"}')
        self.assertEqual(sent["TRUSTED_CONTEXT"]["options"], {"regimes": "eu, us"})
        self.assertNotIn("tests/**", json.dumps(sent))

    def test_build_writes_default_option(self):
        sent = self.build("")
        self.assertEqual(sent["TRUSTED_CONTEXT"]["options"], {"regimes": "undeclared"})


if __name__ == "__main__":
    unittest.main()

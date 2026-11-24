"""Test the havel persona contract: manifest, review prompt, and reply rules.

The source workflow sent AUDIT.md alone. The hub points at the scope
profiles, the regime deltas, and the scope boundary. Those files reach the
model only inside a bundle, so the review mode must send one.
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "engine"
PERSONA_DIR = REPO_ROOT / "reviewers" / "havel"
REVIEW_MODE = "privacy"
DISCLAIMER = "NOT LEGAL ADVICE: engineering findings from a static review. Confirm with counsel."
LOCAL_MODES = {
    "file": ("File", "RISK"),
    "piece": ("Piece", "RISK (partial)"),
    "wholesale": ("Wholesale", "RISK"),
    "data-map": ("Data-map", "ACCURACY"),
}
COVERAGE = "**Mode:** PR\nScope: app.py.\nUnseen: callers.\n"
JSON_LINE = (
    'VERDICT_JSON: {"mode": "PR", "regimes": [], "regime_source": "undeclared", "verdict": "APPROVE", "findings": []}'
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reviewers = _load("reviewers")
persona_hooks = _load("persona_hooks")


def _manifest() -> dict:
    return json.loads((PERSONA_DIR / "reviewer.json").read_text(encoding="utf-8"))


def _review_prompt() -> str:
    return reviewers.load_prompt(PERSONA_DIR, _manifest()["modes"][REVIEW_MODE]["prompt"])


def _regime_files() -> list[Path]:
    directory = PERSONA_DIR / "docs" / "regimes"
    return sorted(path for path in directory.glob("*.md") if path.name not in {"README.md", "scope-profiles.md"})


class ManifestTest(unittest.TestCase):
    """reviewer.json passes the engine schema and declares the havel modes."""

    def test_manifest_passes_the_engine_schema(self):
        self.assertEqual(reviewers.validate_persona(PERSONA_DIR), [])

    def test_privacy_is_the_default_review_mode(self):
        mode = _manifest()["modes"][REVIEW_MODE]
        self.assertIs(mode.get("review"), True)
        self.assertIs(mode.get("default"), True)
        self.assertIs(mode.get("require_coverage"), True)
        self.assertEqual(mode.get("json_mode"), "PR")

    def test_review_findings_carry_the_regime_key(self):
        rules = _manifest()["modes"][REVIEW_MODE]["finding_rules"]
        self.assertEqual(set(rules["keys"]), {"severity", "class", "regime", "file", "line", "title"})
        self.assertEqual(rules["severities"], ["CRITICAL", "HIGH", "MEDIUM", "LOW"])
        self.assertEqual(rules["class_prefix"], "2.")

    def test_local_modes_keep_the_section_6_verdict_lines(self):
        modes = _manifest()["modes"]
        for name, (json_mode, verdict_line) in LOCAL_MODES.items():
            with self.subTest(mode=name):
                self.assertIs(modes[name].get("local"), True)
                self.assertEqual(modes[name]["json_mode"], json_mode)
                self.assertEqual(modes[name]["verdict_line"], verdict_line)

    def test_regimes_is_a_trusted_string_option(self):
        option = _manifest()["options"]["regimes"]
        self.assertEqual(option["type"], "string")
        self.assertIs(option["trusted"], True)

    def test_baseline_and_undeclared_scopes_carry_notes(self):
        notes = _manifest()["option_notes"]["regimes"]
        self.assertEqual(set(notes), {"baseline", "undeclared"})
        self.assertEqual(reviewers.option_notes(_manifest(), {"regimes": "undeclared"}), [notes["undeclared"]])


class ReviewPromptTest(unittest.TestCase):
    """The review mode sends the scope profiles, every regime, and the boundary."""

    def test_every_mode_sends_the_full_all_regime_bundle(self):
        for name, mode in _manifest()["modes"].items():
            with self.subTest(mode=name):
                self.assertEqual(mode["prompt"], "bundles/all-full.md")

    def test_prompt_carries_every_file_the_hub_points_at(self):
        prompt = _review_prompt()
        sources = [PERSONA_DIR / "docs" / "regimes" / "scope-profiles.md", PERSONA_DIR / "docs" / "scope-boundary.md"]
        checks = sorted((PERSONA_DIR / "docs" / "checks").glob("2.*.md"))
        self.assertEqual(len(checks), 29)
        for path in sources + _regime_files() + checks:
            with self.subTest(source=path.name):
                body = path.read_text(encoding="utf-8").strip()
                self.assertIn(body, prompt)

    def test_scope_arrives_through_the_trusted_option(self):
        prompt = _review_prompt()
        self.assertIn("TRUSTED_CONTEXT.options.regimes", prompt)
        self.assertNotIn("A workflow input arrives as the `DECLARED_SCOPE:` line", prompt)

    def test_trusted_option_outranks_the_bundle_header(self):
        self.assertIn(
            "TRUSTED_CONTEXT.options.regimes takes precedence over the `DECLARED_SCOPE:` line of the bundle header",
            _review_prompt(),
        )

    def test_disclaimer_precedes_the_verdict_line(self):
        prompt = _review_prompt()
        self.assertIn("emit this exact line immediately before the verdict line", prompt)
        self.assertNotIn("Then emit this exact final line", prompt)


class ReplyRuleTest(unittest.TestCase):
    """validate_reply requires the disclaimer directly above the final verdict line."""

    @classmethod
    def setUpClass(cls):
        cls.hooks = persona_hooks.load_review_hooks(PERSONA_DIR)

    def reply(self, *middle: str) -> str:
        return "\n".join([COVERAGE.rstrip("\n"), "No findings.", *middle, JSON_LINE]) + "\n"

    def problems(self, response: str) -> list[str]:
        return self.hooks.validate_reply({}, response, {})

    def test_havel_reads_no_repository_file_beyond_the_diff(self):
        self.assertFalse(hasattr(self.hooks, "case_context"))
        self.assertFalse(hasattr(self.hooks, "forced_verdict"))

    def test_disclaimer_above_the_verdict_passes(self):
        self.assertEqual(self.problems(self.reply(DISCLAIMER, "VERDICT: APPROVE - no personal data")), [])

    def test_missing_disclaimer_is_a_problem(self):
        self.assertTrue(self.problems(self.reply("VERDICT: APPROVE - no personal data")))

    def test_disclaimer_away_from_the_verdict_is_a_problem(self):
        response = self.reply(DISCLAIMER, "Summary.", "VERDICT: APPROVE - no personal data")
        self.assertTrue(self.problems(response))

    def test_altered_disclaimer_text_is_a_problem(self):
        response = self.reply("NOT LEGAL ADVICE: compliant.", "VERDICT: APPROVE - no personal data")
        self.assertTrue(self.problems(response))

    def test_quoted_disclaimer_above_an_earlier_verdict_does_not_count(self):
        response = self.reply(DISCLAIMER, "VERDICT: BLOCK - quoted", "Body.", "VERDICT: APPROVE - final")
        self.assertTrue(self.problems(response))


if __name__ == "__main__":
    unittest.main()

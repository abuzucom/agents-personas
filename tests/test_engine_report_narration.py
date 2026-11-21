"""Test the no-self-narration rule in the engine report contract.

A review states its coverage in two noun-only lines, Scope: and Unseen:.
A line outside a code fence that opens with a review-process verb narrates
the review and fails validation. The engine then retries the chunk once.
"""
import importlib.util
import json
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
NARRATION_OPENERS = ("Reviewed", "Examined", "Inspected", "Traced", "Checked", "Analyzed", "Verified",
                     "Looked", "Went", "Started", "Review covered", "The review")
LINE_PREFIXES = ("", "- ", "* ", "1. ", "  ")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load("check_review_response")
call_model = _load("call_model")


def _response(report: str) -> str:
    """Return a report that ends in the two verdict lines."""
    payload = {"mode": "PR", "verdict": "APPROVE", "findings": []}
    return "\n".join([report, "VERDICT: APPROVE", "VERDICT_JSON: " + json.dumps(payload)]) + "\n"


class ProcessOpenerTest(unittest.TestCase):
    """A line that opens with a review-process verb fails validation."""

    def test_each_opener_fails_with_its_line_number(self):
        for opener in NARRATION_OPENERS:
            for prefix in LINE_PREFIXES:
                report = f"**Mode:** PR\n{prefix}{opener} all 18 changed files in the diff."
                with self.subTest(opener=opener, prefix=prefix):
                    self.assertEqual(validator.process_narration_lines(_response(report)), [2])
                    with self.assertRaisesRegex(validator.ResponseError, "process narration appears on report line"):
                        validator.validate_response(_response(report))

    def test_lowercase_opener_fails(self):
        self.assertEqual(validator.process_narration_lines(_response("reviewed the workflow.")), [1])

    def test_fenced_opener_passes(self):
        report = "**Mode:** PR\n```\nReviewed-by: quoted commit trailer\n```"
        self.assertEqual(validator.process_narration_lines(_response(report)), [])

    def test_longer_word_with_an_opener_prefix_passes(self):
        for statement in ("Checkedness stays unchanged.", "Verifiedness flags stay set.", "Lookedup is a name."):
            with self.subTest(statement=statement):
                self.assertEqual(validator.process_narration_lines(_response(statement)), [])


class CoverageLineTest(unittest.TestCase):
    """The structured coverage lines pass the narration check."""

    def test_scope_and_unseen_lines_pass(self):
        report = ("**Mode:** PR\nScope: 18 changed files, PR title, PR body.\n"
                  "Unseen: unchanged callers, CI results.\n[No confirmed findings]")
        self.assertEqual(validator.validate_response(_response(report))[0], "APPROVE")


class FormatSuffixTest(unittest.TestCase):
    """The trusted format suffix names both coverage lines and forbids narration."""

    def test_suffix_requires_scope_and_unseen_after_the_mode_line(self):
        suffix = call_model.REPORT_FORMAT_SUFFIX
        self.assertIn("`Scope:`", suffix)
        self.assertIn("`Unseen:`", suffix)
        self.assertLess(suffix.index("**Mode:**"), suffix.index("`Scope:`"))
        self.assertLess(suffix.index("`Scope:`"), suffix.index("`Unseen:`"))

    def test_suffix_names_every_forbidden_opener(self):
        for opener in NARRATION_OPENERS:
            with self.subTest(opener=opener):
                self.assertIn(opener, call_model.REPORT_FORMAT_SUFFIX)


if __name__ == "__main__":
    unittest.main()

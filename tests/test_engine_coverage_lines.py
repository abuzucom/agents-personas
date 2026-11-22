"""Test the coverage-line check behind the require_coverage mode flag.

A review mode with require_coverage opens its report with three lines: the
mode line with nothing after the mode value, a Scope: line, and an Unseen:
line. A missing or malformed line fails like process narration. The engine
retries once, then records NEEDS-HUMAN with the findings of the retry.
"""

import json
import unittest
from pathlib import Path

from tests import test_engine_run_review as fixture

validator = fixture.run_review.check_review_response
reviewers = fixture.run_review.reviewers
REPO_ROOT = Path(__file__).resolve().parent.parent
COVERED = "**Mode:** PR\nScope: app.py.\nUnseen: callers.\n"


def _reply(opening: str, verdict: str = "APPROVE", findings=None) -> str:
    payload = {"mode": "PR", "verdict": verdict, "findings": findings or []}
    return f"{opening}[No confirmed findings]\nVERDICT: {verdict}\nVERDICT_JSON: {json.dumps(payload)}\n"


class CoverageCheckTest(unittest.TestCase):
    """validate_response checks the three opening lines when asked."""

    def test_bold_and_plain_mode_lines_pass(self):
        for opening in (
            COVERED,
            "Mode: PR\nScope: app.py.\nUnseen: callers.\n",
            "**Mode:** PR\n\nScope: app.py.\n\nUnseen: none.\n",
        ):
            with self.subTest(opening=opening):
                self.assertEqual(
                    validator.validate_response(_reply(opening), "PR", require_coverage=True)[0], "APPROVE"
                )

    def test_malformed_openings_fail_as_coverage_errors(self):
        openings = {
            "missing scope": "**Mode:** PR\nUnseen: callers.\n",
            "missing unseen": "**Mode:** PR\nScope: app.py.\n",
            "reordered": "**Mode:** PR\nUnseen: callers.\nScope: app.py.\n",
            "empty scope": "**Mode:** PR\nScope:\nUnseen: callers.\n",
            "text after the mode": "Mode: PR, all 20 changed files\nScope: app.py.\nUnseen: callers.\n",
            "no mode line": "Scope: app.py.\nUnseen: callers.\n",
            "wrong mode value": "**Mode:** File\nScope: app.py.\nUnseen: callers.\n",
        }
        for name, opening in openings.items():
            with self.subTest(case=name):
                with self.assertRaises(validator.CoverageError) as caught:
                    validator.validate_response(_reply(opening), "PR", require_coverage=True)
                self.assertIsInstance(caught.exception, validator.NarrationError)
                self.assertIn("coverage", str(caught.exception))

    def test_mode_value_is_free_without_an_expected_mode(self):
        opening = "**Mode:** File\nScope: app.py.\nUnseen: callers.\n"
        payload_free = _reply(opening).replace('"mode": "PR", ', "")
        self.assertEqual(validator.validate_response(payload_free, None, require_coverage=True)[0], "APPROVE")

    def test_check_is_off_by_default(self):
        self.assertEqual(validator.validate_response(_reply(""), "PR")[0], "APPROVE")

    def test_allow_narration_also_skips_the_coverage_check(self):
        verdict, _payload = validator.validate_response(_reply(""), "PR", require_coverage=True, allow_narration=True)
        self.assertEqual(verdict, "APPROVE")


class ManifestFlagTest(unittest.TestCase):
    """require_coverage is a boolean mode key, and both shipped review modes set it."""

    def test_flag_must_be_boolean(self):
        self.assertIn("require_coverage", reviewers.MODE_KEYS)
        self.assertIn("require_coverage", reviewers.MODE_FLAGS)

    def test_shipped_review_modes_require_coverage(self):
        for persona, mode in (("foucault", "security"), ("euler", "quality")):
            with self.subTest(persona=persona):
                manifest = json.loads((REPO_ROOT / "reviewers" / persona / "reviewer.json").read_text())
                self.assertIs(manifest["modes"][mode]["require_coverage"], True)


class EngineCoverageTest(unittest.TestCase):
    """run_review retries a missing coverage line, then keeps the findings."""

    tearDown = fixture.RunReviewTest.tearDown
    script = fixture.RunReviewTest.script
    options = fixture.RunReviewTest.options
    prompts = fixture.RunReviewTest.prompts

    def setUp(self):
        fixture.RunReviewTest.setUp(self)
        manifest_path = self.root / "reviewers" / "euler" / "reviewer.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["modes"]["quality"]["require_coverage"] = True
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_covered_reply_keeps_its_verdict(self):
        self.script(_reply(COVERED))
        self.assertEqual(fixture.run_review.run_mode(self.options())["verdict"], "APPROVE")

    def test_missing_lines_retry_with_a_coverage_note(self):
        self.script(_reply("Mode: PR\n"), _reply(COVERED))
        self.assertEqual(fixture.run_review.run_mode(self.options())["verdict"], "APPROVE")
        self.assertIn("coverage", self.prompts()[1])

    def test_two_uncovered_replies_record_needs_human_with_findings(self):
        finding = {"file": "app.py", "line": 1, "severity": "HIGH", "title": "t"}
        self.script(_reply("Mode: PR\n"), _reply("Mode: PR\n", "APPROVE", [finding]))
        result = fixture.run_review.run_mode(self.options())
        self.assertEqual((result["verdict"], result["findings"]), ("NEEDS-HUMAN", [finding]))
        stored = json.loads((self.out / "result.json").read_text(encoding="utf-8"))
        self.assertIn("coverage", stored["chunk_results"][0]["reason"])


if __name__ == "__main__":
    unittest.main()

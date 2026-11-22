"""Test the narration fallback in engine/run_review.py.

A reply that narrates gets one retry. When the retry still narrates and
passes every other check, the chunk records NEEDS-HUMAN with that reply's
report and findings. A person decides on the findings. Any other invalid
reply after the retry still fails the run.
"""

import json
import os
import unittest

from tests import test_engine_run_review as fixture

NARRATION = "Reviewed every changed file.\n"


def _narrating(verdict: str, findings=None) -> str:
    return NARRATION + fixture._reply(verdict, findings)


def _finding() -> dict:
    return {"file": "app.py", "line": 1, "severity": "HIGH", "class": "M14", "title": "t"}


class NarrationFallbackTest(unittest.TestCase):
    """A second narrating reply keeps its findings under NEEDS-HUMAN."""

    tearDown = fixture.RunReviewTest.tearDown
    script = fixture.RunReviewTest.script
    options = fixture.RunReviewTest.options
    prompts = fixture.RunReviewTest.prompts

    def setUp(self):
        # Hosts without bubblewrap fall back to the plain child. CI sets 1 and keeps the sandbox required.
        if "PERSONAS_REQUIRE_SANDBOX" not in os.environ:
            os.environ["PERSONAS_REQUIRE_SANDBOX"] = "0"
            self.addCleanup(os.environ.pop, "PERSONAS_REQUIRE_SANDBOX", None)
        fixture.RunReviewTest.setUp(self)

    def stored(self) -> dict:
        return json.loads((self.out / "result.json").read_text(encoding="utf-8"))

    def test_two_narrating_replies_record_needs_human_with_findings(self):
        second = _narrating("APPROVE", [_finding()])
        self.script(_narrating("APPROVE"), second)
        result = fixture.run_review.run_mode(self.options())
        self.assertEqual(result["verdict"], "NEEDS-HUMAN")
        self.assertEqual(result["findings"], [_finding()])
        entry = self.stored()["chunk_results"][0]
        self.assertEqual(entry["report"], second)
        self.assertIn("process narration after one retry", entry["reason"])

    def test_narrating_block_records_needs_human_without_confirmation(self):
        self.script(_narrating("BLOCK", [_finding()]), _narrating("BLOCK", [_finding()]))
        result = fixture.run_review.run_mode(self.options())
        self.assertEqual(result["verdict"], "NEEDS-HUMAN")
        self.assertEqual(len(self.prompts()), 2)

    def test_narration_then_a_missing_verdict_fails_the_run(self):
        self.script(_narrating("APPROVE"), "no verdict here")
        with self.assertRaisesRegex(fixture.run_review.ReviewError, "invalid response after one retry"):
            fixture.run_review.run_mode(self.options())

    def test_narration_with_invalid_json_fails_the_run(self):
        broken = NARRATION + "Mode: PR\nVERDICT: APPROVE\nVERDICT_JSON: {not json\n"
        self.script(_narrating("APPROVE"), broken)
        with self.assertRaisesRegex(fixture.run_review.ReviewError, "invalid response after one retry"):
            fixture.run_review.run_mode(self.options())

    def test_persona_rejection_of_the_narrating_reply_fails_the_run(self):
        persona_dir = self.root / "reviewers" / "euler"
        (persona_dir / "review_hooks.py").write_text(
            "def validate_reply(payload, response, envelope):\n    return ['persona rule']\n", encoding="utf-8"
        )
        self.script(_narrating("APPROVE"), _narrating("APPROVE"))
        with self.assertRaisesRegex(fixture.run_review.ReviewError, "persona rule"):
            fixture.run_review.run_mode(self.options())

    def test_narration_then_a_persona_rejection_fails_the_run(self):
        # The first reply narrates. The second reply narrates no line but
        # fails a persona rule. The fallback must not reach the first reply.
        persona_dir = self.root / "reviewers" / "euler"
        (persona_dir / "review_hooks.py").write_text(
            "def validate_reply(payload, response, envelope):\n    return ['persona rule']\n", encoding="utf-8"
        )
        self.script(_narrating("APPROVE"), fixture._reply("APPROVE"))
        with self.assertRaisesRegex(fixture.run_review.ReviewError, "invalid response after one retry: persona rule"):
            fixture.run_review.run_mode(self.options())

    def test_clean_retry_keeps_its_own_verdict(self):
        self.script(_narrating("APPROVE"), fixture._reply("APPROVE"))
        self.assertEqual(fixture.run_review.run_mode(self.options())["verdict"], "APPROVE")


class ValidatorFlagTest(unittest.TestCase):
    """validate_response can skip only the narration check."""

    def test_allow_narration_returns_the_verdict(self):
        verdict, payload = fixture.run_review.check_review_response.validate_response(
            _narrating("APPROVE", [_finding()]), "PR", allow_narration=True
        )
        self.assertEqual((verdict, payload["findings"]), ("APPROVE", [_finding()]))

    def test_default_still_rejects_narration(self):
        with self.assertRaises(fixture.run_review.check_review_response.ResponseError):
            fixture.run_review.check_review_response.validate_response(_narrating("APPROVE"), "PR")


if __name__ == "__main__":
    unittest.main()

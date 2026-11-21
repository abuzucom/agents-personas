"""Test the BLOCK confirmation in engine/run_review.py.

A model can return BLOCK on one run and APPROVE on the next for the same
input. A chunk BLOCK therefore gets one confirmation run. The BLOCK stands
only when the confirmation run blocks with a finding class from the first
run. Otherwise the chunk records NEEDS-HUMAN for a person to decide.
"""
import json
import unittest

from tests import test_engine_run_review as fixture

CAPACITY_EXIT_CODE = 3


def _finding(finding_class: str, file: str = "app.py") -> dict:
    return {"file": file, "line": 1, "severity": "HIGH", "class": finding_class, "title": "t"}


class BlockConfirmationTest(unittest.TestCase):
    """A BLOCK stands only when a second run repeats one of its finding classes."""

    setUp = fixture.RunReviewTest.setUp
    tearDown = fixture.RunReviewTest.tearDown
    script = fixture.RunReviewTest.script
    options = fixture.RunReviewTest.options
    prompts = fixture.RunReviewTest.prompts

    def stored(self) -> dict:
        return json.loads((self.out / "result.json").read_text(encoding="utf-8"))

    def test_repeated_class_keeps_the_block(self):
        first = fixture._reply("BLOCK", [_finding("M14"), _finding("M3")])
        self.script(first, fixture._reply("BLOCK", [_finding("M3", "other.py")]))
        result = fixture.run_review.run_mode(self.options())
        self.assertEqual(result["verdict"], "BLOCK")
        self.assertEqual(result["findings"], [_finding("M14"), _finding("M3")])
        self.assertEqual(self.stored()["chunk_results"][0]["report"], first)
        self.assertEqual(len(self.prompts()), 2)

    def test_approve_on_confirmation_records_needs_human(self):
        self.script(fixture._reply("BLOCK", [_finding("M14")]), fixture._reply("APPROVE"))
        result = fixture.run_review.run_mode(self.options())
        self.assertEqual(result["verdict"], "NEEDS-HUMAN")
        self.assertEqual(result["findings"], [_finding("M14")])
        reason = self.stored()["chunk_results"][0]["reason"]
        self.assertIn("BLOCK not confirmed", reason)
        self.assertIn("APPROVE", reason)
        self.assertIn(reason, result["reasons"])

    def test_block_with_a_new_class_records_needs_human(self):
        self.script(fixture._reply("BLOCK", [_finding("M14")]), fixture._reply("BLOCK", [_finding("M3")]))
        result = fixture.run_review.run_mode(self.options())
        self.assertEqual(result["verdict"], "NEEDS-HUMAN")
        self.assertIn("BLOCK not confirmed", self.stored()["chunk_results"][0]["reason"])

    def test_capacity_on_confirmation_records_needs_human(self):
        self.script(fixture._reply("BLOCK", [_finding("M14")]), CAPACITY_EXIT_CODE)
        result = fixture.run_review.run_mode(self.options())
        self.assertEqual(result["verdict"], "NEEDS-HUMAN")
        self.assertIn("BLOCK not confirmed", self.stored()["chunk_results"][0]["reason"])

    def test_findings_without_a_class_compare_by_file(self):
        unclassed = {"file": "app.py", "line": 1, "severity": "HIGH", "title": "t"}
        self.script(fixture._reply("BLOCK", [unclassed]), fixture._reply("BLOCK", [dict(unclassed, line=4)]))
        self.assertEqual(fixture.run_review.run_mode(self.options())["verdict"], "BLOCK")

    def test_confirmation_uses_the_same_prompt_and_its_own_files(self):
        self.script(fixture._reply("BLOCK", [_finding("M14")]), fixture._reply("BLOCK", [_finding("M14")]))
        fixture.run_review.run_mode(self.options())
        first, second = self.prompts()
        self.assertEqual(first, second)
        work = self.out / "case" / "envelopes"
        self.assertTrue((work / "001.prompt.0.txt").is_file())
        self.assertTrue((work / "001.confirm.prompt.0.txt").is_file())

    def test_confirmation_usage_adds_to_the_total(self):
        self.script(fixture._reply("BLOCK", [_finding("M14")]), fixture._reply("BLOCK", [_finding("M14")]))
        result = fixture.run_review.run_mode(self.options())
        self.assertEqual(result["usage"], {"input_tokens": 200, "output_tokens": 40})

    def test_approve_and_needs_human_get_no_confirmation(self):
        for verdict in ("APPROVE", "NEEDS-HUMAN"):
            with self.subTest(verdict=verdict):
                (self.adapter_dir / "count.txt").unlink(missing_ok=True)
                (self.adapter_dir / "prompts.log").unlink(missing_ok=True)
                self.script(fixture._reply(verdict))
                self.assertEqual(fixture.run_review.run_mode(self.options())["verdict"], verdict)
                self.assertEqual(len(self.prompts()), 1)


if __name__ == "__main__":
    unittest.main()

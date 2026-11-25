"""Test the separate run sections of a BLOCK confirmation.

A chunk BLOCK gets one confirmation run. The pull request comment shows each
run under its own heading with its own verdict. One fenced block holding both
reports and two verdict lines reads as a contradiction. The stored report
string keeps its combined form. A chunk without a reported confirmation keeps
its single-run entry shape in result.json.
"""

import json
import unittest

from tests import test_engine_run_review as fixture

review_output = fixture._load("review_output")
CAPACITY_EXIT_CODE = 3
FIRST_LABEL = "Run 1"
CONFIRMATION_LABEL = "Run 2 (confirmation)"


def _finding(finding_class: str) -> dict:
    return {"file": "app.py", "line": 1, "severity": "HIGH", "class": finding_class, "title": "t"}


class StoredRunsTest(unittest.TestCase):
    """result.json records each run of a chunk with its own verdict."""

    setUp = fixture.RunReviewTest.setUp
    tearDown = fixture.RunReviewTest.tearDown
    script = fixture.RunReviewTest.script
    options = fixture.RunReviewTest.options

    def stored_chunk(self) -> dict:
        return json.loads((self.out / "result.json").read_text(encoding="utf-8"))["chunk_results"][0]

    def test_confirmed_chunk_records_both_runs(self):
        first = fixture._reply("BLOCK", [_finding("M14")])
        confirmation = fixture._reply("APPROVE")
        self.script(first, confirmation)
        fixture.run_review.run_mode(self.options())
        self.assertEqual(
            self.stored_chunk()["runs"],
            [
                {"label": FIRST_LABEL, "verdict": "BLOCK", "report": first},
                {"label": CONFIRMATION_LABEL, "verdict": "APPROVE", "report": confirmation},
            ],
        )

    def test_single_run_chunk_keeps_shape(self):
        self.script(fixture._reply("APPROVE"))
        fixture.run_review.run_mode(self.options())
        self.assertNotIn("runs", self.stored_chunk())

    def test_reportless_confirmation_keeps_shape(self):
        first = fixture._reply("BLOCK", [_finding("M14")])
        self.script(first, CAPACITY_EXIT_CODE)
        fixture.run_review.run_mode(self.options())
        chunk = self.stored_chunk()
        self.assertNotIn("runs", chunk)
        self.assertEqual(chunk["report"], first)


class RenderRunsTest(unittest.TestCase):
    """The comment gives each run its own heading and fenced report."""

    def result(self, runs: list | None) -> dict:
        chunk = {"name": "001", "verdict": "NEEDS-HUMAN", "report": "combined", "reason": ""}
        if runs is not None:
            chunk["runs"] = runs
        return {
            "persona": "sample",
            "mode": "quality",
            "head_sha": "a" * 40,
            "verdict": "NEEDS-HUMAN",
            "chunk_results": [chunk],
            "reports": ["combined"],
        }

    def test_two_runs_render_separate_sections(self):
        runs = [
            {"label": FIRST_LABEL, "verdict": "BLOCK", "report": "first report\nVERDICT: BLOCK - x"},
            {"label": CONFIRMATION_LABEL, "verdict": "APPROVE", "report": "second report\nVERDICT: APPROVE - y"},
        ]
        body = review_output.comment_body(self.result(runs))
        first_heading = f"#### {FIRST_LABEL}: BLOCK"
        second_heading = f"#### {CONFIRMATION_LABEL}: APPROVE"
        self.assertIn("### Chunk 001: NEEDS-HUMAN", body)
        self.assertLess(body.index("### Chunk 001"), body.index(first_heading))
        self.assertLess(body.index(first_heading), body.index("first report"))
        self.assertLess(body.index("first report"), body.index(second_heading))
        self.assertLess(body.index(second_heading), body.index("second report"))
        # Each run sits in its own fence, so the first fence closes before the second heading.
        self.assertEqual(body[body.index("first report") : body.index(second_heading)].count("```"), 1)
        self.assertNotIn("combined", body.split("### Chunk 001", 1)[1])

    def test_one_run_renders_as_before(self):
        runs = [{"label": FIRST_LABEL, "verdict": "APPROVE", "report": "combined"}]
        self.assertEqual(review_output.comment_body(self.result(runs)), review_output.comment_body(self.result(None)))
        self.assertNotIn("####", review_output.comment_body(self.result(runs)))


if __name__ == "__main__":
    unittest.main()

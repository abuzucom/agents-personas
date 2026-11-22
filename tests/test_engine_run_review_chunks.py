"""Test the per-chunk record and base SHA that engine/run_review.py writes.

The comment shows one verdict heading per chunk. The runner records each
chunk verdict, report, and reason in result.json for that layout.
"""

import json
import unittest

from tests import test_engine_run_review as fixture

CAPACITY_EXIT_CODE = 3


class ChunkResultsTest(unittest.TestCase):
    """result.json carries base_sha and one entry per chunk."""

    setUp = fixture.RunReviewTest.setUp
    tearDown = fixture.RunReviewTest.tearDown
    script = fixture.RunReviewTest.script
    options = fixture.RunReviewTest.options

    def stored(self) -> dict:
        return json.loads((self.out / "result.json").read_text(encoding="utf-8"))

    def test_base_sha_is_recorded(self):
        self.script(fixture._reply("APPROVE"))
        fixture.run_review.run_mode(self.options())
        self.assertEqual(self.stored()["base_sha"], self.base)

    def test_chunk_entry_carries_name_verdict_and_report(self):
        reply = fixture._reply("APPROVE")
        self.script(reply)
        fixture.run_review.run_mode(self.options())
        self.assertEqual(
            self.stored()["chunk_results"], [{"name": "001", "verdict": "APPROVE", "report": reply, "reason": ""}]
        )

    def test_capacity_chunk_carries_its_reason(self):
        self.script(CAPACITY_EXIT_CODE)
        fixture.run_review.run_mode(self.options())
        entry = self.stored()["chunk_results"][0]
        self.assertEqual((entry["verdict"], entry["report"]), ("NEEDS-HUMAN", ""))
        self.assertIn("capacity", entry["reason"])


if __name__ == "__main__":
    unittest.main()

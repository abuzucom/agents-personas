"""Test that euler findings cite a file and a line inside the review target.

quality_reply.py matches the generay reply rules:
- A finding line is a positive integer. A boolean fails.
- A pull request line falls inside a hunk of the file patch. Added and
  context lines both pass.
- A local finding names a target file and a line inside that file.
"""

import json
import sys
import unittest
from pathlib import Path

PERSONA_DIR = Path(__file__).resolve().parent.parent / "reviewers" / "euler"
sys.path.insert(0, str(PERSONA_DIR / "scripts"))

import quality_reply as checker  # resolved through the path set above
import review_envelope  # resolved through the path set above

CLASSES = checker.load_classes(PERSONA_DIR / "QUALITY.md")
PATCH = "--- a/app.py\n+++ b/app.py\n@@ -10,3 +10,4 @@ def handler():\n ctx\n+new\n ctx\n ctx\n"


def _finding(**changes) -> dict:
    finding = {"severity": "HIGH", "class": "M1", "file": "app.py", "line": 11, "title": "t", "confidence": "certain"}
    finding.update(changes)
    return finding


def _engine_context(patch: str = PATCH) -> checker.ReviewContext:
    envelope = {
        "TRUSTED_CONTEXT": {"persona": "euler"},
        "REVIEW_TARGET": {"files": {"app.py": patch}, "prescan": [], "unreviewed": []},
    }
    return checker.context_from_envelope(envelope, [])


def _euler_pr_context() -> checker.ReviewContext:
    envelope = json.loads(review_envelope.build_envelope("PR", {"app.py": PATCH}, "", [], {"chunk": "1/1"}))
    return checker.context_from_envelope(envelope, [])


def _local_context() -> checker.ReviewContext:
    envelope = json.loads(
        review_envelope.build_envelope("File", {"input.py": "one\ntwo\nthree\n"}, "", [], {"chunk": "1/1"})
    )
    return checker.context_from_envelope(envelope, [])


class FindingLocationTest(unittest.TestCase):
    """Findings cite a file and a line inside the review target."""

    def problems(self, context: checker.ReviewContext, **changes) -> list[str]:
        return checker.finding_problems(_finding(**changes), context, CLASSES)

    def test_hunk_lines_pass(self):
        for line in (10, 11, 13):
            with self.subTest(line=line):
                self.assertEqual(self.problems(_engine_context(), line=line), [])

    def test_pr_line_outside_hunk_fails(self):
        for context in (_engine_context(), _euler_pr_context()):
            for line in (9, 14, 500):
                with self.subTest(line=line):
                    self.assertIn(
                        f"finding line {line} is outside the review target for app.py",
                        self.problems(context, line=line),
                    )

    def test_line_must_positive_integer(self):
        for line in (0, -3, True, "11"):
            with self.subTest(line=line):
                self.assertIn("finding line must be a positive integer", self.problems(_engine_context(), line=line))

    def test_local_finding_needs_file_target(self):
        for file in ("", "other.py"):
            with self.subTest(file=file):
                problems = self.problems(_local_context(), file=file, line=1)
                self.assertTrue(any("outside the review target" in item for item in problems), problems)

    def test_local_line_inside_file(self):
        self.assertEqual(self.problems(_local_context(), file="input.py", line=3), [])
        self.assertIn(
            "finding line 4 is outside the review target for input.py",
            self.problems(_local_context(), file="input.py", line=4),
        )

    def test_non_string_file_reports(self):
        for file in (["app.py"], {"path": "app.py"}, None):
            with self.subTest(file=file):
                self.assertIn("finding file must be a string", self.problems(_engine_context(), file=file))


if __name__ == "__main__":
    unittest.main()

"""Test the generay script fixes that follow the PR 19 persona reviews.

- validate_registry.py reports deep nesting as a validation error.
- validate_registry.py exits with a named status on an unsupported schema.
- time_reply.py requires every finding to cite a file and a line inside
  the review target. A PR line must fall inside a hunk of the file patch.
  A local line must fall inside the file.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "reviewers" / "generay" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import time_reply  # resolved through the path set above
import validate_registry as registry  # resolved through the path set above

CHECKS = time_reply.load_checks()
PATCH = "--- a/app.py\n+++ b/app.py\n@@ -10,3 +10,4 @@ def handler():\n ctx\n+new\n ctx\n ctx\n"
NESTED_SCHEMA = {"$defs": {"node": {"type": "array", "items": {"$ref": "#/$defs/node"}}},
                 "$ref": "#/$defs/node"}


def _nested_list(depth: int) -> list:
    value: list = []
    for _ in range(depth):
        value = [value]
    return value


def _finding(**changes) -> dict:
    check = CHECKS["C9.1"]
    finding = {"severity": "LOW", "check": "C9.1", "method": check.method, "file": "app.py", "line": 11,
               "title": "naive now", "confidence": "certain"}
    finding.update(changes)
    return finding


def _engine_context() -> time_reply.ReviewContext:
    envelope = {"TRUSTED_CONTEXT": {"persona": "generay"},
                "REVIEW_TARGET": {"files": {"app.py": PATCH}, "prescan": [], "unreviewed": []}}
    return time_reply.context_from_envelope(envelope, [])


def _local_context() -> time_reply.ReviewContext:
    envelope = {"mode": "File", "TRUSTED_CONTEXT": {"prescan": []},
                "REVIEW_TARGET": {"files": {"input.py": "one\ntwo\nthree\n"}}}
    return time_reply.context_from_envelope(envelope, [])


class RegistryNestingTest(unittest.TestCase):
    """Deep nesting returns a validation error, not a RecursionError."""

    def test_nesting_past_the_limit_is_a_validation_error(self):
        value = _nested_list(registry.MAX_NESTING_DEPTH + 1)
        errors = registry.validate(value, NESTED_SCHEMA, NESTED_SCHEMA)
        self.assertEqual(len(errors), 1)
        self.assertIn(f"nesting exceeds {registry.MAX_NESTING_DEPTH} levels", errors[0])

    def test_far_deeper_nesting_still_returns_an_error(self):
        errors = registry.validate(_nested_list(sys.getrecursionlimit() * 2), NESTED_SCHEMA, NESTED_SCHEMA)
        self.assertEqual(len(errors), 1)

    def test_nesting_at_the_limit_passes(self):
        value = _nested_list(registry.MAX_NESTING_DEPTH)
        self.assertEqual(registry.validate(value, NESTED_SCHEMA, NESTED_SCHEMA), [])


class RegistryExitStatusTest(unittest.TestCase):
    """main returns the named status for an unsupported schema."""

    def test_unsupported_schema_returns_the_named_status(self):
        with tempfile.TemporaryDirectory() as temp:
            schema = Path(temp) / "schema.json"
            schema.write_text(json.dumps({"oneOf": []}), encoding="utf-8")
            data = Path(temp) / "data.json"
            data.write_text("{}", encoding="utf-8")
            argv = ["validate_registry.py", "--schema", str(schema), "--registry", str(data)]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(io.StringIO()):
                status = registry.main()
        self.assertEqual(status, registry.EXIT_UNSUPPORTED_SCHEMA)
        self.assertNotIn(status, (0, 1))


class FindingLocationTest(unittest.TestCase):
    """Findings cite a file and a line inside the review target."""

    def problems(self, context: time_reply.ReviewContext, **changes) -> list[str]:
        return time_reply.finding_problems(_finding(**changes), context, CHECKS)

    def test_added_and_context_lines_inside_the_hunk_pass(self):
        for line in (10, 11, 13):
            with self.subTest(line=line):
                self.assertEqual(self.problems(_engine_context(), line=line), [])

    def test_pr_line_outside_every_hunk_fails(self):
        for line in (9, 14, 500):
            with self.subTest(line=line):
                self.assertIn(f"finding line {line} is outside the review target for app.py",
                              self.problems(_engine_context(), line=line))

    def test_line_must_be_a_positive_integer(self):
        for line in (0, -3, True, "11"):
            with self.subTest(line=line):
                self.assertIn("finding line must be a positive integer",
                              self.problems(_engine_context(), line=line))

    def test_unhashable_file_is_a_problem_not_a_crash(self):
        for file in (["app.py"], {"path": "app.py"}):
            with self.subTest(file=file):
                problems = self.problems(_engine_context(), file=file)
                self.assertIn(f"finding cites {file} outside the changed files", problems)

    def test_local_finding_needs_a_file_in_the_target(self):
        for file in (None, "", "other.py"):
            with self.subTest(file=file):
                problems = self.problems(_local_context(), file=file, line=1)
                self.assertTrue(any("outside the review target" in item for item in problems), problems)

    def test_local_line_must_fall_inside_the_file(self):
        self.assertEqual(self.problems(_local_context(), file="input.py", line=3), [])
        self.assertIn("finding line 4 is outside the review target for input.py",
                      self.problems(_local_context(), file="input.py", line=4))


if __name__ == "__main__":
    unittest.main()

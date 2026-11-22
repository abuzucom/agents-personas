"""Test the review cache key in engine/review_key.py.

The workflow stores the key in the external_id of each check run. A rerun
with the same key reuses that check run and calls no model. The key covers
every input that changes the review, so a changed input never reuses a
stale verdict.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
FIELDS = {
    "PERSONA": "euler",
    "MODE": "quality",
    "HEAD_SHA": "a" * 40,
    "BASE_SHA": "b" * 40,
    "PERSONAS_REF": "c" * 40,
    "PR_TITLE": "Title",
    "PR_BODY": "Body text",
    "PERSONA_OPTIONS": "",
    "MAX_CHUNKS": "",
    "MAX_ENVELOPE_BYTES": "",
    "MODEL_CALL_COMMAND": "",
    "FAIL_ON_BLOCK": "true",
}


def _load():
    spec = importlib.util.spec_from_file_location("review_key", ENGINE_DIR / "review_key.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


review_key = _load()


class ReviewKeyTest(unittest.TestCase):
    """The key is stable for equal inputs and changes with any input."""

    def test_equal_inputs_give_the_same_key(self):
        self.assertEqual(review_key.review_key(dict(FIELDS)), review_key.review_key(dict(FIELDS)))

    def test_key_has_a_version_prefix_and_a_sha256_digest(self):
        key = review_key.review_key(FIELDS)
        prefix, _, digest = key.partition(":")
        self.assertEqual(prefix, review_key.KEY_VERSION)
        self.assertRegex(digest, "^[0-9a-f]{64}$")

    def test_each_field_changes_the_key(self):
        original = review_key.review_key(FIELDS)
        for name in review_key.KEY_FIELDS:
            with self.subTest(field=name):
                self.assertNotEqual(review_key.review_key({**FIELDS, name: FIELDS[name] + "x"}), original)

    def test_model_command_and_block_gate_are_key_fields(self):
        # The adapter command changes the verdict. fail_on_block changes the
        # conclusion of a BLOCK. A cached result must match both.
        self.assertIn("MODEL_CALL_COMMAND", review_key.KEY_FIELDS)
        self.assertIn("FAIL_ON_BLOCK", review_key.KEY_FIELDS)
        changed = {**FIELDS, "FAIL_ON_BLOCK": "false"}
        self.assertNotEqual(review_key.review_key(changed), review_key.review_key(FIELDS))

    def test_title_and_body_boundary_cannot_shift(self):
        moved = {**FIELDS, "PR_TITLE": "TitleBody", "PR_BODY": " text"}
        self.assertNotEqual(review_key.review_key(moved), review_key.review_key(FIELDS))

    def test_key_holds_no_pull_request_text(self):
        key = review_key.review_key({**FIELDS, "PR_TITLE": "secret-looking title"})
        self.assertNotIn("secret", key)

    def test_missing_field_is_refused(self):
        partial = dict(FIELDS)
        del partial["PERSONAS_REF"]
        with self.assertRaisesRegex(review_key.ReviewKeyError, "PERSONAS_REF"):
            review_key.review_key(partial)


class CliTest(unittest.TestCase):
    """The CLI writes key=<value> to GITHUB_OUTPUT from the environment."""

    def test_cli_writes_the_key_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.txt"
            environment = {**os.environ, **FIELDS, "GITHUB_OUTPUT": str(output)}
            completed = subprocess.run(
                [sys.executable, str(ENGINE_DIR / "review_key.py")],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), f"key={review_key.review_key(FIELDS)}\n")

    def test_cli_without_a_field_fails(self):
        environment = {key: value for key, value in os.environ.items() if key not in FIELDS}
        completed = subprocess.run(
            [sys.executable, str(ENGINE_DIR / "review_key.py")],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("PERSONA", completed.stderr)


if __name__ == "__main__":
    unittest.main()

"""Check the exemption manifest digests against the workflow files in this tree.

The trusted CI scan reads .compliance-tree-exemptions.json from the base
branch. A wrapper edit without a matching digest fails that scan only after
push. This check reports the mismatch and the expected digest locally.
"""

import hashlib
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / ".compliance-tree-exemptions.json"
LOCAL_PREFIX = "./"


def compute_file_sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_reviewed_callers() -> dict:
    """Return the pull_request_target entries of the exemption manifest."""
    return json.loads(MANIFEST_PATH.read_text(encoding="ascii"))["pull_request_target"]


class ExemptionPinTest(unittest.TestCase):
    """Every pinned digest matches the file in this tree."""

    def test_caller_pins_match_files(self) -> None:
        for caller, entry in load_reviewed_callers().items():
            with self.subTest(caller=caller):
                self.assertEqual(entry["sha256"], compute_file_sha256(REPO_ROOT / caller), caller)

    def test_reusable_pins_match_files(self) -> None:
        for caller, entry in load_reviewed_callers().items():
            for target, digest in entry.get("reusable_workflows", {}).items():
                if not target.startswith(LOCAL_PREFIX):
                    continue
                with self.subTest(caller=caller, target=target):
                    path = REPO_ROOT / target[len(LOCAL_PREFIX) :]
                    self.assertEqual(digest, compute_file_sha256(path), target)


if __name__ == "__main__":
    unittest.main()

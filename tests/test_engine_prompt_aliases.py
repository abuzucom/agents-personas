"""Test that a prompt list refuses two spellings of one file.

The duplicate guard compares resolved paths. Spellings such as `A.md` and
`./A.md` name the same file and must not load it twice.
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"


def _load_reviewers():
    spec = importlib.util.spec_from_file_location("reviewers", ENGINE_DIR / "reviewers.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["reviewers"] = module
    spec.loader.exec_module(module)
    return module


reviewers = _load_reviewers()


class PromptAliasTest(unittest.TestCase):
    """prompt_paths refuses a file listed twice under different spellings."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.persona = Path(temp.name)
        (self.persona / "A.md").write_bytes(b"a\n")
        (self.persona / "docs").mkdir()

    def assert_refused(self, prompt: list) -> None:
        with self.assertRaisesRegex(reviewers.ReviewerError, "prompt lists a file twice"):
            reviewers.prompt_paths(self.persona, prompt)

    def test_dot_prefix_alias_is_refused(self):
        self.assert_refused(["A.md", "./A.md"])

    def test_parent_segment_alias_is_refused(self):
        self.assert_refused(["A.md", "docs/../A.md"])

    def test_distinct_files_still_pass(self):
        (self.persona / "B.md").write_bytes(b"b\n")
        paths = reviewers.prompt_paths(self.persona, ["A.md", "B.md"])
        self.assertEqual([path.name for path in paths], ["A.md", "B.md"])


if __name__ == "__main__":
    unittest.main()

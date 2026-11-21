"""Test run_eval.py --extension-root.

The eval-live workflow grades pull request persona data with the grader
from the default branch. --extension-root names the repository root that
supplies eval/extra_checks.py. The --root tree never supplies Python.
"""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tests import test_engine_run_eval as fixture

run_eval = fixture.run_eval
TRUSTED = '''
def validate_expected(mode, expected):
    return []


def grade_response(case, response):
    return [("trusted grader", True, "ran")]
'''


class ExtensionRootTest(unittest.TestCase):
    """The grader loads from --extension-root and never from --root."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.data = fixture.PersonaFixture(str(base / "data"))
        self.data.add_case("review", "block-pr", fixture._expected("BLOCK"))
        self.marker = base / "imported.txt"
        self.data.add_extension(f"open({str(self.marker)!r}, 'w').write('x')\n")
        trusted_dir = base / "trusted" / "reviewers" / "sample" / "eval"
        trusted_dir.mkdir(parents=True)
        (trusted_dir / "extra_checks.py").write_text(TRUSTED, encoding="utf-8")
        self.trusted_root = base / "trusted"

    def run_main(self, *extra: str) -> tuple[int, str]:
        with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()):
            code = run_eval.main(["--persona", "sample", "--root", str(self.data.root),
                                  "--model-call", "tests.test_engine_run_eval_extension_root:block_model", *extra])
        return code, output.getvalue()

    def test_grader_comes_from_the_extension_root(self):
        code, output = self.run_main("--extension-root", str(self.trusted_root))
        self.assertEqual(code, 0, output)
        self.assertIn("trusted grader", output)
        self.assertFalse(self.marker.exists())

    def test_missing_trusted_grader_means_no_extension(self):
        empty = Path(self.temp.name) / "empty"
        empty.mkdir()
        code, output = self.run_main("--extension-root", str(empty))
        self.assertEqual(code, 0, output)
        self.assertNotIn("trusted grader", output)
        self.assertFalse(self.marker.exists())

    def test_without_the_option_the_root_supplies_the_grader(self):
        self.run_main()
        self.assertTrue(self.marker.exists())


def block_model(system_prompt: str, mode: str, case_text: str) -> str:
    """Return a fixed BLOCK reply for the eval fixture."""
    payload = {"mode": mode, "verdict": "BLOCK", "findings": []}
    return f"VERDICT: BLOCK\nVERDICT_JSON: {json.dumps(payload)}\n"


if __name__ == "__main__":
    unittest.main()

"""Test run_eval.py --max-cases.

eval-live pays for one model call per case. --max-cases counts the selected
cases before any model call and fails the run when the count exceeds the
cap. A pull request cannot raise the cap, because the workflow on the
default branch sets it.
"""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tests import test_engine_run_eval as fixture

run_eval = fixture.run_eval
# --model-call can import this module under a second name. A log file keeps
# one count across both module objects.
CALL_LOG_VARIABLE = "MAX_CASES_CALL_LOG"


def counting_model(system_prompt: str, mode: str, case_text: str) -> str:
    """Record each call in the log file and return a BLOCK reply."""
    with open(os.environ[CALL_LOG_VARIABLE], "a", encoding="utf-8") as log:
        log.write(mode + "\n")
    return "VERDICT: BLOCK\n"


class MaxCasesTest(unittest.TestCase):
    """The cap stops a run before its first model call."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = Path(self.temp.name) / "calls.log"
        os.environ[CALL_LOG_VARIABLE] = str(self.log)
        self.addCleanup(os.environ.pop, CALL_LOG_VARIABLE, None)
        self.persona = fixture.PersonaFixture(str(Path(self.temp.name) / "persona"))
        for name in ("one", "two", "three"):
            self.persona.add_case("review", name, fixture._expected("BLOCK"))

    def run_main(self, *extra: str) -> tuple[int, str]:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            try:
                code = run_eval.main(["--persona", "sample", "--root", str(self.persona.root), *extra])
            except SystemExit as exit_error:
                code = exit_error.code
        return code, errors.getvalue()

    def test_over_the_cap_fails_without_a_model_call(self):
        code, errors = self.run_main("--max-cases", "2", "--model-call",
                                     "tests.test_engine_run_eval_max_cases:counting_model")
        self.assertEqual(code, 1)
        self.assertIn("3 case(s) exceed --max-cases 2", errors)
        self.assertFalse(self.log.exists())

    def test_at_the_cap_runs_every_case(self):
        code, _errors = self.run_main("--max-cases", "3", "--model-call",
                                      "tests.test_engine_run_eval_max_cases:counting_model")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.log.read_text(encoding="utf-8").splitlines()), 3)

    def test_invalid_caps_are_refused(self):
        for value in ("0", "-1", "x"):
            with self.subTest(value=value):
                self.assertNotEqual(self.run_main("--max-cases", value)[0], 0)


if __name__ == "__main__":
    unittest.main()

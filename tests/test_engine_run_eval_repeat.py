"""Test the repeated eval run and its agreement report in engine/run_eval.py.

--repeat N sends every case N times. The report gives the share of runs
that return the most common verdict for each case. It also counts the cases
with unanimous runs. A low share marks a case where the model verdict
varies between identical runs.
"""

import io
import itertools
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from tests import test_engine_run_eval as fixture

run_eval = fixture.run_eval


def _cycling_model(replies: list[str]):
    """Return a model callable that cycles through the replies."""
    cycle = itertools.cycle(replies)

    def call_model(system_prompt: str, mode: str, case_text: str) -> str:
        return next(cycle)

    return call_model


class RepeatTest(unittest.TestCase):
    """Each case runs N times and the report states the agreement."""

    def run_cases(self, replies: list[str], repeat: int) -> tuple[int, str, int]:
        calls = []
        model = _cycling_model(replies)

        def call_model(system_prompt: str, mode: str, case_text: str) -> str:
            calls.append(mode)
            return model(system_prompt, mode, case_text)

        with tempfile.TemporaryDirectory() as directory:
            persona = fixture.PersonaFixture(directory)
            persona.add_case("review", "block-pr", fixture._expected("BLOCK"))
            cases, _ = persona.collect(mode="review")
            with redirect_stdout(io.StringIO()) as output:
                failures = run_eval.run_live(persona.persona_dir, persona.manifest, cases, call_model, repeat=repeat)
        return failures, output.getvalue(), len(calls)

    def test_each_case_runs_n_times(self):
        _failures, _output, calls = self.run_cases(["VERDICT: BLOCK\n"], 3)
        self.assertEqual(calls, 3)

    def test_split_verdicts_report_modal_share(self):
        failures, output, _calls = self.run_cases(["VERDICT: BLOCK\n", "VERDICT: APPROVE\n", "VERDICT: BLOCK\n"], 3)
        self.assertEqual(failures, 1)
        self.assertIn("agreement review/block-pr: 2/3 BLOCK", output)
        self.assertIn("0/1 case(s) agree on every run", output)

    def test_unanimous_runs_report_full_agreement(self):
        _failures, output, _calls = self.run_cases(["VERDICT: BLOCK\n"], 2)
        self.assertIn("agreement review/block-pr: 2/2 BLOCK", output)
        self.assertIn("1/1 case(s) agree on every run", output)

    def test_missing_verdict_counts_separately(self):
        _failures, output, _calls = self.run_cases(["no verdict\n", "VERDICT: BLOCK\n"], 2)
        self.assertIn("agreement review/block-pr: 1/2", output)

    def test_single_run_skips_agreement(self):
        _failures, output, _calls = self.run_cases(["VERDICT: BLOCK\n"], 1)
        self.assertNotIn("agreement", output)


class RepeatOptionTest(unittest.TestCase):
    """The CLI bounds --repeat and requires a model call for it."""

    def run_main(self, *arguments: str) -> tuple[int, str]:
        with redirect_stderr(io.StringIO()) as errors, redirect_stdout(io.StringIO()):
            try:
                code = run_eval.main(["--persona", "euler", *arguments])
            except SystemExit as exit_error:
                code = exit_error.code
        return code, errors.getvalue()

    def test_repeat_without_model_call_fails(self):
        code, errors = self.run_main("--repeat", "3")
        self.assertEqual(code, 1)
        self.assertIn("--repeat needs --model-call", errors)

    def test_repeat_outside_the_bounds_fails(self):
        for value in ("0", str(run_eval.MAX_REPEAT + 1), "x"):
            with self.subTest(value=value):
                self.assertNotEqual(self.run_main("--repeat", value)[0], 0)


if __name__ == "__main__":
    unittest.main()

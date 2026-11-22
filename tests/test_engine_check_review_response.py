"""Test the shared review response validator in engine/check_review_response.py.

The cases from the foucault validator carry over. New cases cover the
engine-specific rules: a caller-supplied mode, persona-specific extra keys,
and finding locations.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
VALIDATOR_PATH = ENGINE_DIR / "check_review_response.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("check_review_response", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_validator()
ResponseError = validator.ResponseError


def _response(report: str, verdict: str = "APPROVE", findings=None, **extra) -> str:
    """Return a report that ends in the two verdict lines."""
    payload = {"mode": "PR", "verdict": verdict, "findings": findings or []}
    payload.update(extra)
    lines = [report] if report else []
    lines += [f"VERDICT: {verdict}", "VERDICT_JSON: " + json.dumps(payload)]
    return "\n".join(lines) + "\n"


def _finding(**changes) -> dict:
    finding = {"severity": "HIGH", "class": "2.1", "file": "app.py", "line": 3, "title": "t"}
    finding.update(changes)
    return finding


class VerdictContractTest(unittest.TestCase):
    """The final verdict lines follow one contract for every persona."""

    def test_accepts_each_verdict_value(self):
        for verdict in ("APPROVE", "BLOCK", "NEEDS-HUMAN"):
            with self.subTest(verdict=verdict):
                found, _payload = validator.validate_response(_response("Scope: one file.", verdict))
                self.assertEqual(found, verdict)

    def test_accepts_a_verdict_reason_suffix(self):
        response = _response("Scope: one file.").replace("VERDICT: APPROVE", "VERDICT: APPROVE - no findings")
        self.assertEqual(validator.validate_response(response)[0], "APPROVE")

    def test_rejects_an_unknown_verdict_token(self):
        response = _response("Scope.").replace("VERDICT: APPROVE", "VERDICT: REJECT")
        with self.assertRaisesRegex(ResponseError, "malformed"):
            validator.validate_response(response)

    def test_rejects_a_missing_verdict_line(self):
        response = 'No verdict.\nVERDICT_JSON: {"mode": "PR", "verdict": "APPROVE", "findings": []}\n'
        with self.assertRaisesRegex(ResponseError, "no VERDICT line"):
            validator.validate_response(response)

    def test_rejects_an_empty_response(self):
        with self.assertRaisesRegex(ResponseError, "empty"):
            validator.validate_response("")

    def test_rejects_json_that_disagrees_with_the_verdict_line(self):
        response = _response("Scope.").replace('"verdict": "APPROVE"', '"verdict": "BLOCK"')
        with self.assertRaisesRegex(ResponseError, "does not match"):
            validator.validate_response(response)

    def test_rejects_text_after_the_json_line(self):
        with self.assertRaisesRegex(ResponseError, "final report line"):
            validator.validate_response(_response("Scope.") + "Trailing note.\n")

    def test_rejects_json_that_does_not_follow_the_verdict_line(self):
        response = _response("Scope.").replace("\nVERDICT_JSON", "\n\nVERDICT_JSON")
        with self.assertRaisesRegex(ResponseError, "immediately follow"):
            validator.validate_response(response)

    def test_rejects_json_that_is_not_an_object(self):
        response = "Scope.\nVERDICT: APPROVE\nVERDICT_JSON: [1]\n"
        with self.assertRaisesRegex(ResponseError, "not an object"):
            validator.validate_response(response)

    def test_rejects_an_oversized_response(self):
        report = "x" * (validator.RESPONSE_LIMIT + 1)
        with self.assertRaisesRegex(ResponseError, "limit"):
            validator.validate_response(_response(report))

    def test_reads_the_last_verdict_line_like_the_gate(self):
        response = "VERDICT: BLOCK\nScope.\n" + _response("")
        self.assertEqual(validator.validate_response(response)[0], "APPROVE")


class ModeAndKeysTest(unittest.TestCase):
    """The caller names the expected mode. Personas may add keys."""

    def test_expected_mode_must_match(self):
        with self.assertRaisesRegex(ResponseError, "mode 'PR' does not match expected mode 'time'"):
            validator.validate_response(_response("Scope."), expected_mode="time")

    def test_matching_expected_mode_passes(self):
        verdict, payload = validator.validate_response(_response("Scope."), expected_mode="PR")
        self.assertEqual((verdict, payload["mode"]), ("APPROVE", "PR"))

    def test_persona_specific_keys_pass_through(self):
        response = _response("Scope.", schema_version="1", prescan=[])
        _verdict, payload = validator.validate_response(response)
        self.assertEqual(payload["schema_version"], "1")

    def test_missing_findings_key_is_rejected(self):
        response = 'Scope.\nVERDICT: APPROVE\nVERDICT_JSON: {"verdict": "APPROVE"}\n'
        with self.assertRaisesRegex(ResponseError, "findings"):
            validator.validate_response(response)


class FindingLocationTest(unittest.TestCase):
    """Every finding names a file and a positive line for annotations."""

    def test_valid_finding_passes(self):
        verdict, payload = validator.validate_response(_response("Scope.", "BLOCK", [_finding()]))
        self.assertEqual((verdict, len(payload["findings"])), ("BLOCK", 1))

    def test_finding_without_file_is_rejected(self):
        with self.assertRaisesRegex(ResponseError, "file"):
            validator.validate_response(_response("Scope.", "BLOCK", [_finding(file="")]))

    def test_finding_with_zero_line_is_rejected(self):
        with self.assertRaisesRegex(ResponseError, "line"):
            validator.validate_response(_response("Scope.", "BLOCK", [_finding(line=0)]))

    def test_finding_with_boolean_line_is_rejected(self):
        with self.assertRaisesRegex(ResponseError, "line"):
            validator.validate_response(_response("Scope.", "BLOCK", [_finding(line=True)]))

    def test_finding_that_is_not_an_object_is_rejected(self):
        with self.assertRaisesRegex(ResponseError, "object"):
            validator.validate_response(_response("Scope.", "BLOCK", ["text"]))


class NarrationTest(unittest.TestCase):
    """First-person process narration fails. Impersonal statements pass."""

    def test_impersonal_statements_pass(self):
        for statement in (
            "i.e. the diff adds a test.",
            "Trace: base to sink is parameterized.",
            "Inspect results: none.",
            "Inputs stay unchanged.",
        ):
            with self.subTest(statement=statement):
                self.assertEqual(validator.validate_response(_response(statement))[0], "APPROVE")

    def test_first_person_narration_fails_with_line_number(self):
        for statement in (
            "I need to inspect the helper.",
            "- We checked the caller.",
            "Let me trace the filename.",
            "Now I inspect the caller.",
        ):
            with self.subTest(statement=statement):
                with self.assertRaisesRegex(ResponseError, "process narration appears on report line"):
                    validator.validate_response(_response(statement))

    def test_fenced_first_person_text_passes(self):
        response = _response("Scope.\n```\nI am quoted evidence.\n```")
        self.assertEqual(validator.process_narration_lines(response), [])


class CliTest(unittest.TestCase):
    """The CLI prints the normalized verdict or fails."""

    def run_cli(self, text: str, *arguments: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "response.txt"
            path.write_bytes(text.encode("utf-8"))
            return subprocess.run(
                [sys.executable, str(VALIDATOR_PATH), str(path), *arguments],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_valid_response_prints_verdict(self):
        result = self.run_cli(_response("Scope.", "BLOCK", [_finding()]), "--mode", "PR")
        self.assertEqual((result.returncode, result.stdout), (0, "VERDICT: BLOCK\n"))

    def test_invalid_response_fails(self):
        result = self.run_cli("no verdict\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid review response", result.stderr)

    def test_bare_carriage_return_stays_inside_one_line(self):
        response = _response("Scope.").replace("VERDICT: APPROVE\n", "VERDICT: APPROVE\rX\n")
        result = self.run_cli(response)
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()

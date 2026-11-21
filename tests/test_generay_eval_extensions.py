"""Test reviewers/generay/eval/extra_checks.py, the generay eval extension."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTENSION_PATH = REPO_ROOT / "reviewers" / "generay" / "eval" / "extra_checks.py"


def _load():
    spec = importlib.util.spec_from_file_location("generay_extra_checks", EXTENSION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extension = _load()


def _expected(**changes) -> dict:
    expected = {"mode": "File", "expected_verdict": "RISK: HIGH", "expected_checks": ["C9.1"],
                "expected_prescan": [], "expect_json": True, "notes": "n"}
    expected.update(changes)
    return expected


def _reply(checks=(), escalations=()) -> str:
    payload = {"schema_version": "1", "mode": "File", "verdict": "HIGH",
               "findings": [{"check": item} for item in checks],
               "escalations": [{"check": item, "decision": "d"} for item in escalations], "prescan": []}
    return f"RISK: HIGH\nVERDICT_JSON: {json.dumps(payload)}\n"


class ValidateExpectedTest(unittest.TestCase):
    """validate_expected enforces the generay expected.json rules."""

    def test_valid_expected_passes(self):
        self.assertEqual(extension.validate_expected("file", _expected()), [])

    def test_unknown_check_is_reported(self):
        problems = extension.validate_expected("file", _expected(expected_checks=["C99.9"]))
        self.assertIn("unknown check 'C99.9' in expected_checks", problems)

    def test_pr_case_with_prescan_is_reported(self):
        problems = extension.validate_expected("time", _expected(expected_prescan=["C9.1"]))
        self.assertIn("PR cases carry no head tree, so expected_prescan must be empty", problems)

    def test_missing_and_mistyped_keys_are_reported(self):
        expected = _expected()
        del expected["expected_prescan"]
        self.assertEqual(extension.validate_expected("file", expected), ["missing key 'expected_prescan'"])
        self.assertIn("expect_json must be a boolean", extension.validate_expected("file", _expected(expect_json=1)))


class ValidateCaseTest(unittest.TestCase):
    """validate_case compares the scanner output with expected_prescan."""

    def case(self, text: str, expected_prescan: list[str]) -> dict:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        case_dir = Path(temp.name)
        (case_dir / "input.py").write_text(text, encoding="utf-8")
        return {"name": "c", "dir": str(case_dir), "mode": "file", "files": ["input.py"],
                "expected": _expected(expected_prescan=expected_prescan)}

    def test_matching_prescan_passes(self):
        # A module-level now() also hits C18.3, module-scope now.
        case = self.case("from datetime import datetime\nx = datetime.now()\n", ["C9.1", "C18.3"])
        self.assertEqual(extension.validate_case(case), [])

    def test_scanner_mismatch_is_reported(self):
        case = self.case("from datetime import datetime\nx = datetime.now()\n", [])
        self.assertIn("scanner reported unexpected check C9.1", extension.validate_case(case))

    def test_pr_case_needs_a_diff(self):
        case = {"mode": "time", "files": ["input.py"], "expected": _expected()}
        self.assertEqual(extension.validate_case(case), ["PR mode requires diff.patch"])


class GradeResponseTest(unittest.TestCase):
    """grade_response checks the expected check IDs in findings and escalations."""

    def test_check_in_findings_or_escalations_passes(self):
        case = {"expected": _expected(expected_checks=["C9.1", "C14.6"])}
        grades = extension.grade_response(case, _reply(["C9.1"], ["C14.6"]))
        self.assertEqual(grades, [("checks", True, "expected checks reported")])

    def test_missing_check_fails(self):
        grades = extension.grade_response({"expected": _expected()}, _reply())
        self.assertEqual(grades, [("checks", False, "missing C9.1")])


if __name__ == "__main__":
    unittest.main()

"""Test reviewers/adorno/eval/extra_checks.py, the adorno eval extension."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTENSION_PATH = REPO_ROOT / "reviewers" / "adorno" / "eval" / "extra_checks.py"


def _load():
    spec = importlib.util.spec_from_file_location("adorno_extra_checks", EXTENSION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extension = _load()


def _expected(**changes) -> dict:
    expected = {"mode": "File", "expected_verdict": "RISK: HIGH", "expected_classes": ["2.1"], "notes": "n"}
    expected.update(changes)
    return expected


class ValidateExpectedTest(unittest.TestCase):
    """validate_expected applies the adorno corpus rules."""

    def test_valid_expected_passes(self):
        self.assertEqual(extension.validate_expected("file", _expected()), [])

    def test_missing_expected_classes_is_reported(self):
        expected = _expected()
        del expected["expected_classes"]
        self.assertEqual(extension.validate_expected("file", expected), ["missing key 'expected_classes'"])

    def test_expected_classes_must_list(self):
        self.assertIn(
            "expected_classes must be a list", extension.validate_expected("file", _expected(expected_classes="2.1"))
        )

    def test_unknown_class_is_reported(self):
        problems = extension.validate_expected("file", _expected(expected_classes=["2.99", "9.1"]))
        self.assertIn("unknown class '2.99' in expected_classes", problems)
        self.assertIn("unknown class '9.1' in expected_classes", problems)

    def test_non_string_class_is_problem(self):
        problems = extension.validate_expected("file", _expected(expected_classes=["2.1", {"id": "2.1"}, 2]))
        self.assertEqual(
            problems,
            ["expected_classes entries must be strings: {'id': '2.1'}", "expected_classes entries must be strings: 2"],
        )

    def test_non_ascii_needs_fixture_notes(self):
        problems = extension.validate_expected("file", _expected(allow_non_ascii=True))
        self.assertIn("allow_non_ascii: true requires fixture_notes explaining why", problems)
        self.assertEqual(extension.validate_expected("file", _expected(allow_non_ascii=True, fixture_notes="n")), [])

    def test_blank_notes_leave_non_ascii(self):
        for notes in ("", "  ", 3):
            with self.subTest(notes=notes):
                problems = extension.validate_expected("file", _expected(allow_non_ascii=True, fixture_notes=notes))
                self.assertIn("allow_non_ascii: true requires fixture_notes explaining why", problems)

    def test_blank_notes_are_reported(self):
        self.assertIn("notes must be a non-empty string", extension.validate_expected("file", _expected(notes=" ")))


class ValidateCaseTest(unittest.TestCase):
    """validate_case accepts only the input names the adorno runner reads."""

    def case(self, *names: str) -> dict:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for name in names:
            (Path(temp.name) / name).write_text("x\n", encoding="utf-8")
        return {"name": "c", "dir": temp.name, "mode": "file", "files": list(names), "expected": _expected()}

    def test_recognized_input_passes(self):
        self.assertEqual(extension.validate_case(self.case("input.tsx")), [])
        self.assertEqual(extension.validate_case(self.case("spec.md", "input.css")), [])

    def test_case_without_recognized_input_reported(self):
        self.assertEqual(
            extension.validate_case(self.case("notes.txt")), ["no recognized input file present: notes.txt"]
        )


class KnownClassesTest(unittest.TestCase):
    """The known class set comes from the AUDIT.md section 2 headings."""

    def test_section_two_heading_known(self):
        self.assertEqual(len(extension.KNOWN_CLASSES), 23)
        self.assertIn("2.23", extension.KNOWN_CLASSES)


if __name__ == "__main__":
    unittest.main()

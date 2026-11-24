"""Test reviewers/havel/eval/extra_checks.py, the havel eval extension."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "engine"
EXTENSION_PATH = REPO_ROOT / "reviewers" / "havel" / "eval" / "extra_checks.py"
DISCLAIMER = "NOT LEGAL ADVICE: engineering findings from a static review. Confirm with counsel."


def _load():
    if str(ENGINE_DIR) not in sys.path:
        sys.path.insert(0, str(ENGINE_DIR))
    spec = importlib.util.spec_from_file_location("havel_extra_checks", EXTENSION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extension = _load()


def _expected(**changes) -> dict:
    expected = {
        "mode": "File",
        "declared_scope": "eu",
        "expected_verdict": "RISK:",
        "expected_classes": ["2.1", "2.1@gdpr"],
        "expected_regimes": ["gdpr", "eprivacy", "eidas"],
        "expected_regime_source": "declared",
        "expect_json": True,
        "notes": "n",
        "fixture_notes": "Synthetic data.",
    }
    expected.update(changes)
    return expected


def _case(**changes) -> dict:
    return {
        "name": "c",
        "mode": "file",
        "prompt_mode": "File",
        "expected": _expected(**changes),
        "context": "",
        "hook_context": "",
        "case_text": "x = 1\n",
        "files": ["input.py"],
    }


def _reply(label: str = "RISK", disclaimer: bool = True, **payload_changes) -> str:
    payload = {
        "mode": "File",
        "regimes": ["eidas", "eprivacy", "gdpr"],
        "regime_source": "declared",
        "verdict": "HIGH",
        "findings": [{"severity": "HIGH", "class": "2.1", "regime": ["gdpr"], "file": "a.py", "line": 1, "title": "t"}],
    }
    payload.update(payload_changes)
    notice = f"{DISCLAIMER}\n" if disclaimer else ""
    return f"Findings.\n{notice}{label}: HIGH - no basis\nVERDICT_JSON: {json.dumps(payload)}\n"


def _grades(response: str, **changes) -> dict:
    return {label: (passed, detail) for label, passed, detail in extension.grade_response(_case(**changes), response)}


class ValidateExpectedTest(unittest.TestCase):
    """validate_expected applies the havel corpus and scope rules."""

    def test_valid_expected_passes(self):
        self.assertEqual(extension.validate_expected("file", _expected()), [])

    def test_unknown_class_is_reported(self):
        problems = extension.validate_expected("file", _expected(expected_classes=["2.99"]))
        self.assertIn("unknown class '2.99' in expected_classes", problems)

    def test_delta_token_needs_a_known_slug(self):
        problems = extension.validate_expected("file", _expected(expected_classes=["2.1@atlantis"]))
        self.assertIn("expected_classes token '2.1@atlantis' needs the form 2.N@slug with a known slug", problems)

    def test_regimes_beyond_the_declared_scope_are_reported(self):
        problems = extension.validate_expected("file", _expected(expected_regimes=["ccpa"]))
        self.assertIn("expected_regimes names ccpa beyond the reach of declared_scope 'eu'", problems)

    def test_undeclared_scope_reaches_no_regime(self):
        problems = extension.validate_expected("file", _expected(declared_scope="undeclared"))
        self.assertIn("declared_scope is undeclared and expected_regimes is non-empty", problems)

    def test_unknown_scope_name_is_reported(self):
        problems = extension.validate_expected("file", _expected(declared_scope="mars"))
        self.assertTrue(any("scope 'mars' matches no profile" in problem for problem in problems), problems)

    def test_unknown_regime_source_is_reported(self):
        problems = extension.validate_expected("file", _expected(expected_regime_source="guessed"))
        self.assertTrue(any("expected_regime_source 'guessed'" in problem for problem in problems), problems)

    def test_fixture_notes_are_required(self):
        problems = extension.validate_expected("file", _expected(fixture_notes=" "))
        self.assertIn("fixture_notes must state that the fixture data is synthetic", problems)


class ValidateCaseTest(unittest.TestCase):
    """validate_case accepts only the input names the havel runner reads."""

    def test_recognized_input_passes(self):
        self.assertEqual(extension.validate_case({"files": ["ropa.json", "input.py"]}), [])

    def test_unrecognized_input_is_reported(self):
        self.assertEqual(
            extension.validate_case({"files": ["input.rb"]}), ["no recognized input file present: input.rb"]
        )


class BuildModelInputTest(unittest.TestCase):
    """build_model_input carries the declared scope in TRUSTED_CONTEXT."""

    def test_declared_scope_joins_trusted_context(self):
        envelope = json.loads(extension.build_model_input(_case(), "prompt"))
        self.assertEqual(envelope["TRUSTED_CONTEXT"], {"options": {"regimes": "eu"}})
        self.assertNotIn("eu", envelope["REVIEW_TARGET"]["text"])

    def test_ask_branch_case_carries_no_trusted_context(self):
        case = _case()
        del case["expected"]["declared_scope"]
        self.assertNotIn("TRUSTED_CONTEXT", json.loads(extension.build_model_input(case, "prompt")))


class GradeResponseTest(unittest.TestCase):
    """grade_response checks the disclaimer and the companion classes and scope."""

    def test_complete_reply_passes_every_grade(self):
        grades = _grades(_reply())
        self.assertTrue(all(passed for passed, _detail in grades.values()), grades)

    def test_missing_disclaimer_fails(self):
        self.assertFalse(_grades(_reply(disclaimer=False))["not-legal-advice line"][0])

    def test_disclaimer_follows_the_mode_verdict_label(self):
        self.assertFalse(_grades(_reply(label="VERDICT"))["not-legal-advice line"][0])

    def test_missing_regime_delta_fails(self):
        finding = {"severity": "HIGH", "class": "2.1", "regime": ["baseline"], "file": "a.py", "line": 1, "title": "t"}
        passed, detail = _grades(_reply(findings=[finding]))["havel classes and scope"]
        self.assertFalse(passed)
        self.assertIn("2.1@gdpr", detail)

    def test_wrong_regime_scope_fails(self):
        passed, detail = _grades(_reply(regimes=["ucpa"]))["havel classes and scope"]
        self.assertFalse(passed)
        self.assertIn("differ from expected", detail)

    def test_wrong_regime_source_fails(self):
        self.assertFalse(_grades(_reply(regime_source="undeclared"))["havel classes and scope"][0])


if __name__ == "__main__":
    unittest.main()

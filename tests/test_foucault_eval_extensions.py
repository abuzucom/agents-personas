"""Test reviewers/foucault/eval/extra_checks.py through engine/run_eval.py."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "engine"
PERSONA_DIR = REPO_ROOT / "reviewers" / "foucault"
CASES_DIR = PERSONA_DIR / "eval" / "cases"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reviewers = _load("reviewers")
run_eval = _load("run_eval")
extension = run_eval.load_extension(PERSONA_DIR)
MANIFEST = reviewers.read_manifest(PERSONA_DIR)


def _case(mode: str, name: str) -> dict:
    case, findings = run_eval.load_case(CASES_DIR / mode / name, mode, MANIFEST["modes"][mode], extension)
    assert not findings, findings
    return case


def _report(findings: list, prior: str = "Prior finding 2.5 at app.py:3 remains open.") -> str:
    payload = {"mode": "PR", "verdict": "BLOCK", "findings": findings}
    return f"Mode: PR\n{prior}\nVERDICT: BLOCK - injection\nVERDICT_JSON: {json.dumps(payload)}\n"


class CorpusTest(unittest.TestCase):
    """The imported corpus keeps all 68 cases, sorted by mode."""

    def test_case_counts_per_mode(self):
        counts = {mode: len([path for path in (CASES_DIR / mode).iterdir() if path.is_dir()])
                  for mode in MANIFEST["modes"]}
        self.assertEqual(counts, {"security": 21, "file": 45, "piece": 1, "wholesale": 1})

    def test_case_tree_has_no_findings(self):
        _cases, findings = run_eval.collect_cases(PERSONA_DIR, MANIFEST, extension=extension)
        self.assertEqual(findings, [])


class StructureExtensionTest(unittest.TestCase):
    """foucault rejects other review statuses and malformed report contracts."""

    def contract_case(self) -> dict:
        return copy.deepcopy(_case("security", "report-process-narration-pr")["expected"])

    def test_review_status_other_than_needs_human_is_reported(self):
        expected = {"expected_review_status": "COMPLETE"}
        self.assertEqual(extension.validate_expected("security", expected),
                         ["expected_review_status must be NEEDS-HUMAN"])

    def test_report_contract_needs_the_security_mode(self):
        findings = extension.validate_expected("file", self.contract_case())
        self.assertEqual(findings, ["report_contract requires a JSON-enabled security case"])

    def test_report_contract_shape_and_flags(self):
        expected = self.contract_case()
        expected["report_contract"]["forbid_process_narration"] = False
        self.assertIn("report_contract must forbid process narration",
                      extension.validate_expected("security", expected))
        expected["report_contract"]["extra"] = True
        self.assertEqual(extension.validate_expected("security", expected),
                         ["report_contract has an invalid shape"])

    def test_required_finding_class_and_line(self):
        expected = self.contract_case()
        expected["report_contract"]["required_finding"].update({"class": "9.9", "line": 0})
        findings = extension.validate_expected("security", expected)
        self.assertIn("required_finding class must appear in expected_classes", findings)
        self.assertIn("required_finding line is invalid", findings)


class InputExtensionTest(unittest.TestCase):
    """omit_provenance sends the bare target. Other cases use the engine envelope."""

    def test_omit_provenance_case_sends_bare_text(self):
        cases = [case for mode in MANIFEST["modes"] for case in run_eval.collect_cases(
            PERSONA_DIR, MANIFEST, mode=mode, extension=extension)[0] if case["expected"].get("omit_provenance")]
        self.assertEqual(len(cases), 1)
        envelope = json.loads(extension.build_model_input(cases[0], "prompt"))
        self.assertEqual(set(envelope), {"mode", "text"})

    def test_ordinary_case_uses_the_default(self):
        self.assertIsNone(extension.build_model_input(_case("security", "sql-injection-pr"), "prompt"))


class GradeExtensionTest(unittest.TestCase):
    """VERDICT_JSON needs the exact foucault keys. Report contracts need evidence."""

    def test_json_shape_requires_exact_keys_and_mode(self):
        case = _case("security", "sql-injection-pr")
        good = 'VERDICT: BLOCK\nVERDICT_JSON: {"mode": "PR", "verdict": "BLOCK", "findings": []}\n'
        extra = 'VERDICT: BLOCK\nVERDICT_JSON: {"mode": "PR", "verdict": "BLOCK", "findings": [], "x": 1}\n'
        wrong_mode = 'VERDICT: BLOCK\nVERDICT_JSON: {"mode": "Diff", "verdict": "BLOCK", "findings": []}\n'
        self.assertTrue(extension.grade_response(case, good)[0][1])
        self.assertFalse(extension.grade_response(case, extra)[0][1])
        self.assertFalse(extension.grade_response(case, wrong_mode)[0][1])

    def test_report_contract_passes_with_status_and_required_finding(self):
        case = _case("security", "report-process-narration-pr")
        required = case["expected"]["report_contract"]["required_finding"]
        finding = {"severity": "HIGH", "title": "Defect", **required}
        grades = dict((label, passed) for label, passed, _ in extension.grade_response(case, _report([finding])))
        self.assertEqual(grades, {"VERDICT_JSON shape": True, "report contract": True})

    def test_report_contract_fails_without_prior_status_or_finding(self):
        case = _case("security", "report-process-narration-pr")
        grades = extension.grade_response(case, _report([], prior="Scope: one file."))
        label, passed, detail = grades[-1]
        self.assertEqual((label, passed), ("report contract", False))
        self.assertIn("prior finding status is absent", detail)
        self.assertIn("required finding evidence is absent", detail)


if __name__ == "__main__":
    unittest.main()

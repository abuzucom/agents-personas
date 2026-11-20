"""Test reviewers/euler/eval/extra_checks.py through engine/run_eval.py.

Ported from abuzucom/euler tests/test_run_eval.py, test_eval_false_positives.py,
and test_review_narration.py at 9488a8c. A temporary euler persona holds the
cases. It reuses the committed manifest, prompt, scripts, and extension.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "engine"
PERSONA_DIR = REPO_ROOT / "reviewers" / "euler"


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

GOOD_PR_RESPONSE = """[HIGH] app.py:3 - Swallowed error
  Class: M1 Blocking.

VERDICT: BLOCK - M1 swallowed exception on the write path.
VERDICT_JSON: {"schema_version": "1", "mode": "PR", "verdict": "BLOCK", "findings": [{"severity": "HIGH", "class": "M1", "file": "app.py", "line": 3, "title": "Swallowed error", "confidence": "certain"}], "prescan": []}
"""


def _json_line(mode: str, verdict: str, findings="[]") -> str:
    return (f'VERDICT_JSON: {{"schema_version":"1","mode":"{mode}","verdict":"{verdict}",'
            f'"findings":{findings},"prescan":[]}}\n')


class CaseFixture(unittest.TestCase):
    """Write cases into a temporary copy of the euler persona."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.persona_dir = Path(self.temp.name) / "euler"
        self.persona_dir.mkdir()
        for name in ("reviewer.json", "QUALITY.md"):
            shutil.copy2(PERSONA_DIR / name, self.persona_dir / name)

    def write_case(self, mode: str, slug: str, expected: dict, files: dict[str, str]) -> Path:
        case_dir = self.persona_dir / "eval" / "cases" / mode / slug
        case_dir.mkdir(parents=True)
        (case_dir / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
        for name, content in files.items():
            (case_dir / name).write_text(content, encoding="utf-8")
        return case_dir

    def findings(self) -> list[str]:
        return run_eval.collect_cases(self.persona_dir, MANIFEST, extension=extension)[1]

    def load(self, mode: str, slug: str) -> dict:
        case, findings = run_eval.load_case(self.persona_dir / "eval" / "cases" / mode / slug, mode,
                                            MANIFEST["modes"][mode], extension)
        assert not findings, findings
        return case

    def failures(self, case: dict, response: str) -> list[str]:
        grades = run_eval.grade_response(case, response, MANIFEST["modes"][case["mode"]], extension)
        return [f"{label}: {detail}" for label, passed, detail in grades if not passed]

    @staticmethod
    def valid_expected(**overrides) -> dict:
        expected = {"mode": "PR", "expected_verdict": "BLOCK", "expected_classes": ["M1"],
                    "expect_json": True, "notes": "The handler swallows the error."}
        expected.update(overrides)
        return expected


class StructureTest(CaseFixture):
    """euler structure rules join the engine rules."""

    def test_repository_corpus_is_valid(self):
        _cases, findings = run_eval.collect_cases(PERSONA_DIR, MANIFEST, extension=extension)
        self.assertEqual(findings, [])

    def test_valid_case_passes(self):
        self.write_case("quality", "ok-pr", self.valid_expected(), {"diff.patch": "--- a/x\n+++ b/x\n"})
        self.assertEqual(self.findings(), [])

    def test_bad_mode_fails(self):
        self.write_case("quality", "bad-mode", self.valid_expected(mode="Diff"), {"diff.patch": ""})
        self.assertIn("quality/bad-mode: mode 'Diff' does not match 'PR'", self.findings())

    def test_unknown_class_fails(self):
        self.write_case("quality", "bad-class", self.valid_expected(expected_classes=["Z9"]), {"diff.patch": ""})
        self.assertIn("quality/bad-class: unknown class 'Z9'", self.findings())

    def test_missing_fixture_fails(self):
        self.write_case("quality", "no-diff", self.valid_expected(), {"input.py": "x = 1\n"})
        self.assertIn("quality/no-diff: PR mode requires diff.patch", self.findings())

    def test_non_pr_case_needs_an_input_file(self):
        expected = self.valid_expected(mode="File", expected_verdict="RISK: HIGH")
        self.write_case("file", "no-input", expected, {"diff.patch": "+x\n"})
        self.assertIn("file/no-input: non-PR mode requires an input.<ext> file", self.findings())

    def test_verdict_mode_mismatch_fails(self):
        self.write_case("quality", "mismatch", self.valid_expected(expected_verdict="RISK: HIGH"), {"diff.patch": ""})
        self.assertIn("quality/mismatch: expected_verdict 'RISK: HIGH' does not fit mode 'quality'", self.findings())

    def test_empty_notes_fail(self):
        self.write_case("quality", "no-notes", self.valid_expected(notes=""), {"diff.patch": ""})
        self.assertIn("quality/no-notes: notes must be a non-empty string", self.findings())

    def test_expect_json_is_required_and_boolean(self):
        expected = self.valid_expected()
        del expected["expect_json"]
        self.write_case("quality", "no-json", expected, {"diff.patch": ""})
        self.write_case("quality", "text-json", self.valid_expected(expect_json="yes"), {"diff.patch": ""})
        findings = self.findings()
        self.assertIn("quality/no-json: missing key 'expect_json'", findings)
        self.assertIn("quality/text-json: expect_json must be a boolean", findings)

    def test_invalid_active_work_elapsed_fails(self):
        cases = ((True, "bad-timeout-bool"), ("600", "bad-timeout-string"), (-1, "bad-timeout-negative"))
        for value, slug in cases:
            self.write_case("quality", slug, self.valid_expected(active_work_elapsed_seconds=value),
                            {"diff.patch": ""})
        findings = self.findings()
        for _, slug in cases:
            self.assertIn(f"quality/{slug}: active_work_elapsed_seconds must be a non-negative integer", findings)

    def test_bad_review_status_fails(self):
        self.write_case("quality", "bad-status", self.valid_expected(expected_review_status="APPROVE"),
                        {"diff.patch": ""})
        self.assertIn("quality/bad-status: expected_review_status must be NEEDS-HUMAN", self.findings())


class LiveEvaluationTest(CaseFixture):
    """Grades match the euler runner."""

    def test_matching_response_passes(self):
        self.write_case("quality", "ok-pr", self.valid_expected(), {"diff.patch": "+x\n"})
        self.assertEqual(self.failures(self.load("quality", "ok-pr"), GOOD_PR_RESPONSE), [])

    def test_wrong_verdict_fails(self):
        self.write_case("quality", "ok-pr", self.valid_expected(expected_verdict="APPROVE"), {"diff.patch": "+x\n"})
        failures = self.failures(self.load("quality", "ok-pr"), GOOD_PR_RESPONSE)
        self.assertTrue(any(item.startswith("final line") for item in failures), failures)

    def test_missing_class_fails(self):
        self.write_case("quality", "ok-pr", self.valid_expected(expected_classes=["Q4"]), {"diff.patch": "+x\n"})
        failures = self.failures(self.load("quality", "ok-pr"), GOOD_PR_RESPONSE)
        self.assertIn("classes: missing expected class Q4; unexpected class M1", failures)

    def test_unexpected_finding_class_fails_clean_case(self):
        expected = self.valid_expected(expected_verdict="APPROVE", expected_classes=[])
        self.write_case("quality", "resolved-q4-pr", expected, {"diff.patch": "+x\n"})
        response = "VERDICT: APPROVE - The fix resolves division by zero.\n" + _json_line(
            "PR", "APPROVE", '[{"class":"Q4"}]')
        self.assertIn("classes: unexpected class Q4", self.failures(self.load("quality", "resolved-q4-pr"), response))

    def test_case_text_is_the_euler_envelope(self):
        files = {"diff.patch": "+x\n", "context.md": "Adds a handler."}
        self.write_case("quality", "ok-pr", self.valid_expected(), files)
        envelope = json.loads(extension.build_model_input(self.load("quality", "ok-pr"), "prompt"))
        self.assertEqual(envelope["mode"], "PR")
        self.assertEqual(envelope["REVIEW_TARGET"]["files"]["diff.patch"], "+x\n")
        self.assertEqual(envelope["REVIEW_TARGET"]["context"], "Adds a handler.")
        self.assertIn("sha256", envelope["REVIEW_TARGET"])

    def test_non_pr_case_carries_prescan_candidates(self):
        expected = self.valid_expected(mode="File", expected_verdict="RISK: HIGH")
        source = "try:\n    run()\nexcept ValueError:\n    pass\n"
        self.write_case("file", "catch-file", expected, {"input.py": source})
        envelope = json.loads(extension.build_model_input(self.load("file", "catch-file"), "prompt"))
        classes = {item["class"] for item in envelope["TRUSTED_CONTEXT"]["prescan"]}
        self.assertIn("M1", classes)

    def test_timeout_metadata_and_status_are_enforced(self):
        expected = self.valid_expected(expected_verdict="NEEDS-HUMAN", expected_classes=[],
                                       expected_review_status="NEEDS-HUMAN", active_work_elapsed_seconds=600)
        self.write_case("quality", "timeout-pr", expected, {"diff.patch": "+x\n"})
        case = self.load("quality", "timeout-pr")
        envelope = json.loads(extension.build_model_input(case, "prompt"))
        self.assertEqual(envelope["TRUSTED_CONTEXT"]["metadata"]["active_work_elapsed_seconds"], 600)
        response = "VERDICT: NEEDS-HUMAN - active work time limit reached.\n" + _json_line("PR", "NEEDS-HUMAN")
        self.assertTrue(any(item.startswith("REVIEW STATUS") for item in self.failures(case, response)))
        with_status = "REVIEW STATUS: NEEDS-HUMAN - active review time limit reached.\n" + response
        self.assertEqual(self.failures(case, with_status), [])

    def test_verdict_named_only_in_justification_fails(self):
        self.write_case("quality", "ok-pr", self.valid_expected(expected_classes=[]), {"diff.patch": "+x\n"})
        response = "VERDICT: APPROVE - no BLOCK finding.\n" + _json_line("PR", "APPROVE")
        failures = self.failures(self.load("quality", "ok-pr"), response)
        self.assertTrue(any(item.startswith("final line") for item in failures), failures)

    def test_risk_verdict_requires_a_token_boundary(self):
        expected = self.valid_expected(mode="File", expected_verdict="RISK: HIGH", expected_classes=[])
        self.write_case("file", "risk-file", expected, {"input.py": "x = 1\n"})
        case = self.load("file", "risk-file")
        self.assertEqual(self.failures(case, "RISK: HIGH - unchecked divisor.\n" + _json_line("File", "HIGH")), [])
        failures = self.failures(case, "RISK: HIGHER - unchecked divisor.\n" + _json_line("File", "HIGH"))
        self.assertTrue(any(item.startswith("final line") for item in failures), failures)

    def test_null_findings_reported_without_crash(self):
        self.write_case("quality", "ok-pr", self.valid_expected(), {"diff.patch": "+x\n"})
        response = "VERDICT: BLOCK - M1 swallowed exception.\n" + _json_line("PR", "BLOCK", "null")
        self.assertIn("classes: VERDICT_JSON findings must be an array",
                      self.failures(self.load("quality", "ok-pr"), response))

    def test_eval_flags_process_narration_when_requested(self):
        expected = self.valid_expected(expected_verdict="APPROVE", expected_classes=[], forbid_process_narration=True)
        self.write_case("quality", "review-narration-pr", expected, {"diff.patch": "+x\n"})
        report = "Let me inspect the changed code first.\nVERDICT: APPROVE - No confirmed findings.\n" + _json_line(
            "PR", "APPROVE")
        failures = self.failures(self.load("quality", "review-narration-pr"), report)
        self.assertTrue(any(item.startswith("process narration") for item in failures), failures)


if __name__ == "__main__":
    unittest.main()

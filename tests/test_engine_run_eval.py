"""Test engine/run_eval.py: case structure, live grading, and persona extensions."""

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "engine"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reviewers = _load("reviewers")
validator = _load("check_review_response")
run_eval = _load("run_eval")

REVIEW_MODE = {"prompt": "PROMPT.md", "review": True, "default": True, "json_mode": "PR"}
FILE_MODE = {
    "prompt": "PROMPT.md",
    "local": True,
    "json_mode": "File",
    "verdict_line": "RISK",
    "verdicts": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE-FOUND"],
}
EXTENSION = """
def validate_expected(mode, expected):
    return ["needs ticket"] if "ticket" not in expected else []


def grade_response(case, response):
    return [("ticket", case["expected"]["ticket"] in response, "ticket named")]
"""


class PersonaFixture:
    """Build a throwaway persona with a review mode and a local file mode."""

    def __init__(self, directory: str):
        self.root = Path(directory)
        self.persona_dir = self.root / "reviewers" / "sample"
        self.persona_dir.mkdir(parents=True)
        (self.persona_dir / "PROMPT.md").write_text("prompt\n", encoding="ascii")
        manifest = {"persona": "sample", "function": "review", "modes": {"review": REVIEW_MODE, "file": FILE_MODE}}
        (self.persona_dir / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.manifest = manifest

    def add_case(self, mode: str, name: str, expected: object, inputs=("diff.patch",)) -> Path:
        case_dir = self.persona_dir / "eval" / "cases" / mode / name
        case_dir.mkdir(parents=True)
        (case_dir / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
        for input_name in inputs:
            (case_dir / input_name).write_text(f"content of {input_name}\n", encoding="utf-8")
        return case_dir

    def add_extension(self, text: str = EXTENSION) -> None:
        (self.persona_dir / "eval").mkdir(exist_ok=True)
        (self.persona_dir / "eval" / "extra_checks.py").write_text(text, encoding="utf-8")

    def collect(self, **options):
        extension = run_eval.load_extension(self.persona_dir)
        return run_eval.collect_cases(self.persona_dir, self.manifest, extension=extension, **options)


def _expected(verdict: str, mode: str = "PR", **extra) -> dict:
    return {"mode": mode, "expected_verdict": verdict, "expected_classes": [], "notes": "n", **extra}


class StructureTest(unittest.TestCase):
    """Each case needs an expected.json object that fits its mode and one input."""

    def test_valid_review_and_local_cases_load(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            fixture.add_case("review", "block-pr", _expected("BLOCK"))
            fixture.add_case("file", "high-file", _expected("RISK: HIGH", "File"), ("input.py",))
            cases, findings = fixture.collect()
        self.assertEqual(findings, [])
        self.assertEqual([(case["mode"], case["prompt_mode"]) for case in cases], [("review", "PR"), ("file", "File")])
        self.assertTrue(all(Path(case["dir"]).name == case["name"] for case in cases))

    def test_every_local_verdict_spelling_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            for index, verdict in enumerate(("HIGH", "RISK: NONE-FOUND", "RISK", "RISK:")):
                fixture.add_case("file", f"case-{index}", _expected(verdict, "File"))
            cases, findings = fixture.collect()
        self.assertEqual((len(cases), findings), (4, []))

    def test_verdict_outside_the_mode_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            fixture.add_case("file", "approve-file", _expected("APPROVE", "File"))
            fixture.add_case("review", "risk-pr", _expected("RISK: HIGH"))
            _cases, findings = fixture.collect()
        self.assertEqual(len(findings), 2, findings)
        self.assertTrue(all("does not fit mode" in item for item in findings))

    def test_mode_field_must_match_json_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            fixture.add_case("file", "wrong-mode", _expected("RISK: HIGH", "PR"))
            _cases, findings = fixture.collect()
        self.assertTrue(any("does not match 'File'" in item for item in findings), findings)

    def test_missing_keys_non_object_and_no_input_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            fixture.add_case("review", "no-notes", {"expected_verdict": "BLOCK"})
            fixture.add_case("review", "list", ["BLOCK"])
            fixture.add_case("review", "no-input", _expected("BLOCK"), inputs=("context.md",))
            _cases, findings = fixture.collect()
        text = "\n".join(findings)
        self.assertIn("review/no-notes: expected.json lacks 'notes'", text)
        self.assertIn("review/list: expected.json must hold a JSON object", text)
        self.assertIn("review/no-input: holds no input file", text)

    def test_invalid_json_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            case_dir = fixture.add_case("review", "broken", {})
            (case_dir / "expected.json").write_text("{", encoding="utf-8")
            _cases, findings = fixture.collect()
        self.assertTrue(any("not readable UTF-8 JSON" in item for item in findings), findings)

    def test_mode_and_case_filters(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            fixture.add_case("review", "block-pr", _expected("BLOCK"))
            fixture.add_case("file", "high-file", _expected("RISK: HIGH", "File"))
            by_mode, _ = fixture.collect(mode="file")
            by_case, _ = fixture.collect(only="block-pr")
            with self.assertRaisesRegex(run_eval.EvalError, "unknown mode"):
                fixture.collect(mode="wholesale")
            with self.assertRaisesRegex(run_eval.EvalError, "no case named"):
                fixture.collect(only="absent")
        self.assertEqual([case["name"] for case in by_mode], ["high-file"])
        self.assertEqual([case["name"] for case in by_case], ["block-pr"])


class ExtensionTest(unittest.TestCase):
    """A persona extension adds structure findings and response grades."""

    def test_extension_structure_finding_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            fixture.add_extension()
            fixture.add_case("review", "no-ticket", _expected("BLOCK"))
            _cases, findings = fixture.collect()
        self.assertEqual(findings, ["review/no-ticket: needs ticket"])

    def test_validate_case_sees_the_loaded_case(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            fixture.add_extension(
                'def validate_case(case):\n    return [] if "diff.patch" in case["files"] else ["needs diff.patch"]\n'
            )
            fixture.add_case("review", "patch-pr", _expected("BLOCK"))
            fixture.add_case("review", "python-pr", _expected("BLOCK"), inputs=("input.py",))
            cases, findings = fixture.collect()
        self.assertEqual([case["name"] for case in cases], ["patch-pr"])
        self.assertEqual(findings, ["review/python-pr: needs diff.patch"])

    def test_extension_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            target = Path(directory) / "elsewhere.py"
            target.write_text(EXTENSION, encoding="utf-8")
            (fixture.persona_dir / "eval").mkdir()
            try:
                (fixture.persona_dir / "eval" / "extra_checks.py").symlink_to(target)
            except OSError as error:
                self.skipTest(f"platform denied symlink creation: {error}")
            with self.assertRaisesRegex(run_eval.EvalError, "regular file"):
                run_eval.load_extension(fixture.persona_dir)

    def test_extension_grades_join_the_core_grades(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            fixture.add_extension()
            fixture.add_case("review", "ticket-pr", _expected("BLOCK", ticket="T-7"))
            cases, _ = fixture.collect()
            extension = run_eval.load_extension(fixture.persona_dir)
        grades = run_eval.grade_response(cases[0], "T-7\nVERDICT: BLOCK\n", REVIEW_MODE, extension)
        self.assertEqual([(label, passed) for label, passed, _ in grades], [("verdict", True), ("ticket", True)])


class GradingTest(unittest.TestCase):
    """The final verdict line decides the grade. The reason never does."""

    def test_last_verdict_line_decides(self):
        response = "VERDICT: BLOCK\nquoted text\nVERDICT: APPROVE - no BLOCK conditions observed\n"
        self.assertEqual(run_eval.verdict_matches("BLOCK", response, REVIEW_MODE)[0], False)
        self.assertEqual(run_eval.verdict_matches("APPROVE", response, REVIEW_MODE)[0], True)

    def test_local_mode_reads_its_own_verdict_line(self):
        response = "VERDICT: BLOCK\nRISK: HIGH - unsanitized path\n"
        self.assertTrue(run_eval.verdict_matches("RISK: HIGH", response, FILE_MODE)[0])
        self.assertTrue(run_eval.verdict_matches("HIGH", response, FILE_MODE)[0])
        self.assertTrue(run_eval.verdict_matches("RISK:", response, FILE_MODE)[0])
        self.assertFalse(run_eval.verdict_matches("RISK: LOW", response, FILE_MODE)[0])

    def test_local_mode_without_its_line_fails(self):
        passed, detail = run_eval.verdict_matches("HIGH", "VERDICT: BLOCK\n", FILE_MODE)
        self.assertFalse(passed)
        self.assertIn("no 'RISK:' line", detail)

    def test_partial_label_matches_only_its_own_line(self):
        piece = {**FILE_MODE, "verdict_line": "RISK (partial)"}
        self.assertTrue(run_eval.verdict_matches("RISK (partial)", "RISK (partial): MEDIUM\n", piece)[0])
        self.assertFalse(run_eval.verdict_matches("RISK (partial)", "RISK: MEDIUM\n", piece)[0])

    def test_review_status_uses_the_last_status_line(self):
        response = "REVIEW STATUS: NEEDS-HUMAN quoted\nREVIEW STATUS: COMPLETE\n"
        self.assertFalse(run_eval.review_status_matches("NEEDS-HUMAN", response))
        self.assertTrue(run_eval.review_status_matches("COMPLETE", response))

    def test_json_companion_shapes(self):
        good = 'VERDICT_JSON: {"mode": "File", "verdict": "HIGH", "findings": []}'
        self.assertIsNotNone(run_eval.json_companion(good)[0])
        self.assertIsNone(run_eval.json_companion("VERDICT_JSON: [1]")[0])
        self.assertIsNone(run_eval.json_companion('VERDICT_JSON: {"verdict": 3, "findings": []}')[0])
        self.assertIsNone(run_eval.json_companion("VERDICT_JSON: {")[0])
        self.assertIsNone(run_eval.json_companion("no companion")[0])

    def test_grade_response_adds_status_and_json_checks(self):
        case = {"expected": _expected("NEEDS-HUMAN", expect_json=True, expected_review_status="NEEDS-HUMAN")}
        response = (
            "REVIEW STATUS: NEEDS-HUMAN\nVERDICT: NEEDS-HUMAN\n"
            'VERDICT_JSON: {"mode": "PR", "verdict": "NEEDS-HUMAN", "findings": []}\n'
        )
        grades = run_eval.grade_response(case, response, REVIEW_MODE)
        self.assertEqual(
            [(label, passed) for label, passed, _ in grades],
            [("verdict", True), ("REVIEW STATUS", True), ("VERDICT_JSON", True)],
        )


class LiveRunTest(unittest.TestCase):
    """run_live sends the prompt, the prompt mode, and the envelope to the callable."""

    def test_run_live_passes_prompt_mode_and_counts_failures(self):
        calls = []

        def call_model(system_prompt: str, mode: str, case_text: str) -> str:
            calls.append((system_prompt, mode, json.loads(case_text)["mode"]))
            return "RISK: HIGH - finding\n" if mode == "File" else "VERDICT: APPROVE\n"

        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            fixture.add_case("review", "block-pr", _expected("BLOCK"))
            fixture.add_case("file", "high-file", _expected("RISK: HIGH", "File"))
            cases, _ = fixture.collect()
            with redirect_stdout(io.StringIO()) as output:
                failures = run_eval.run_live(fixture.persona_dir, fixture.manifest, cases, call_model)
        self.assertEqual(failures, 1)
        self.assertEqual(sorted(calls), [("prompt\n", "File", "File"), ("prompt\n", "PR", "PR")])
        self.assertIn("1/2 response checks passed", output.getvalue())

    def test_extension_model_input_replaces_the_default_unless_none(self):
        seen = []

        def call_model(system_prompt: str, mode: str, case_text: str) -> str:
            seen.append(case_text)
            return "VERDICT: BLOCK\n"

        with tempfile.TemporaryDirectory() as directory:
            fixture = PersonaFixture(directory)
            fixture.add_extension(
                "def build_model_input(case, system_prompt):\n"
                '    return "plain" if case["name"] == "plain-pr" else None\n'
            )
            fixture.add_case("review", "plain-pr", _expected("BLOCK"))
            fixture.add_case("review", "default-pr", _expected("BLOCK"))
            cases, _ = fixture.collect()
            extension = run_eval.load_extension(fixture.persona_dir)
            with redirect_stdout(io.StringIO()):
                run_eval.run_live(fixture.persona_dir, fixture.manifest, cases, call_model, extension)
        self.assertEqual(seen[1], "plain")
        self.assertIn("REVIEW_TARGET", json.loads(seen[0]))

    def test_default_model_input_labels_target_and_trusted_context(self):
        case = {"prompt_mode": "PR", "context": "ctx", "case_text": "diff", "hook_context": "hook"}
        envelope = json.loads(run_eval.default_model_input(case, "prompt"))
        self.assertEqual(envelope["REVIEW_TARGET"]["text"], "ctx\n\ndiff")
        self.assertIs(envelope["TRUSTED_HOOK_CONTEXT"]["read_only"], True)
        self.assertEqual(envelope["policy_sha256"], run_eval.sha256_text("prompt"))

    def test_model_call_spec_must_name_a_function(self):
        with self.assertRaisesRegex(run_eval.EvalError, "module:function"):
            run_eval.resolve_model_call("json")
        with self.assertRaisesRegex(run_eval.EvalError, "not callable"):
            run_eval.resolve_model_call("json:absent_name")


class EngineVerdictParityTest(unittest.TestCase):
    """Review-mode defaults match the verdicts the CI validator accepts."""

    def test_default_verdicts_match_the_validator(self):
        self.assertEqual(reviewers.DEFAULT_VERDICTS, validator.VERDICTS)


class RepositoryCasesTest(unittest.TestCase):
    """Every committed persona passes the structure check."""

    def test_every_persona_case_tree_is_valid(self):
        for persona in reviewers.list_personas(REPO_ROOT):
            with self.subTest(persona=persona):
                persona_dir, manifest = reviewers.load_persona(REPO_ROOT, persona)
                extension = run_eval.load_extension(persona_dir)
                _cases, findings = run_eval.collect_cases(persona_dir, manifest, extension=extension)
                self.assertEqual(findings, [])

    def test_cli_rejects_an_unknown_persona(self):
        completed = subprocess.run(
            [sys.executable, str(ENGINE_DIR / "run_eval.py"), "--persona", "absent"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("unknown persona", completed.stderr)


if __name__ == "__main__":
    unittest.main()

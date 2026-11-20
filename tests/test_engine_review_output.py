"""Test engine/review_output.py, the check and comment rendering for one mode."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
HEAD_SHA = "a" * 40


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


output = _load("review_output")


def _result(**changes) -> dict:
    result = {
        "persona": "euler", "mode": "quality", "head_sha": HEAD_SHA, "verdict": "BLOCK",
        "reasons": [], "findings": [{"file": "app.py", "line": 4, "severity": "HIGH", "title": "Bad loop"}],
        "changed_files": ["app.py"], "unreviewed": [], "chunks": 2, "clamped": [],
        "usage": {"input_tokens": 1200, "output_tokens": 300}, "duration_seconds": 12.5,
        "reports": ["Mode: PR\nOne finding.\nVERDICT: BLOCK\nVERDICT_JSON: {}"],
    }
    result.update(changes)
    return result


class VerdictCombinationTest(unittest.TestCase):
    """The most severe chunk verdict wins. Unreviewed files forbid APPROVE."""

    def test_most_severe_verdict_wins(self):
        self.assertEqual(output.combine_verdicts(["APPROVE", "BLOCK", "NEEDS-HUMAN"], [])[0], "BLOCK")

    def test_all_approve_stays_approve(self):
        self.assertEqual(output.combine_verdicts(["APPROVE", "APPROVE"], []), ("APPROVE", []))

    def test_unreviewed_files_turn_approve_into_needs_human(self):
        verdict, reasons = output.combine_verdicts(["APPROVE"], ["big.bin"])
        self.assertEqual(verdict, "NEEDS-HUMAN")
        self.assertTrue(any("unreviewed" in reason for reason in reasons))

    def test_unreviewed_files_keep_block(self):
        self.assertEqual(output.combine_verdicts(["BLOCK"], ["big.bin"])[0], "BLOCK")

    def test_no_chunks_and_no_unreviewed_files_approves(self):
        verdict, reasons = output.combine_verdicts([], [])
        self.assertEqual(verdict, "APPROVE")
        self.assertTrue(reasons)

    def test_unknown_verdict_is_rejected(self):
        with self.assertRaises(ValueError):
            output.combine_verdicts(["MAYBE"], [])


class ConclusionTest(unittest.TestCase):
    """fail_on_block gates BLOCK only. NEEDS-HUMAN warns and never blocks (decision 21)."""

    def test_approve_is_success(self):
        self.assertEqual(output.conclusion("APPROVE", True), "success")

    def test_block_fails_when_gating(self):
        self.assertEqual(output.conclusion("BLOCK", True), "failure")

    def test_block_is_neutral_when_not_gating(self):
        self.assertEqual(output.conclusion("BLOCK", False), "neutral")

    def test_needs_human_is_neutral_whatever_fail_on_block_says(self):
        for fail_on_block in (True, False):
            with self.subTest(fail_on_block=fail_on_block):
                self.assertEqual(output.conclusion("NEEDS-HUMAN", fail_on_block), "neutral")


class WarningTest(unittest.TestCase):
    """A NEEDS-HUMAN result carries one warning line for the workflow run."""

    def test_needs_human_renders_a_warning(self):
        rendered = output.render(_result(verdict="NEEDS-HUMAN", findings=[]), fail_on_block=True)
        self.assertEqual(rendered["warning"], output.NEEDS_HUMAN_WARNING.format(check="euler / quality"))

    def test_other_verdicts_render_no_warning(self):
        for verdict in ("APPROVE", "BLOCK"):
            with self.subTest(verdict=verdict):
                self.assertEqual(output.render(_result(verdict=verdict), fail_on_block=True)["warning"], "")

    def test_warning_holds_no_workflow_command_characters(self):
        self.assertNotIn("::", output.NEEDS_HUMAN_WARNING)
        self.assertNotIn("\n", output.NEEDS_HUMAN_WARNING)


class RenderTest(unittest.TestCase):
    """render builds the check run, annotations, comment, and metrics."""

    def test_check_name_and_comment_header(self):
        rendered = output.render(_result(), fail_on_block=True)
        self.assertEqual(rendered["check_name"], "euler / quality")
        first_line = rendered["comment_body"].split("\n", 1)[0]
        self.assertEqual(first_line, f"euler / quality | head {HEAD_SHA} | VERDICT: BLOCK")

    def test_annotation_for_changed_file(self):
        annotation = output.render(_result(), fail_on_block=True)["annotations"][0]
        self.assertEqual((annotation["path"], annotation["start_line"], annotation["end_line"]), ("app.py", 4, 4))
        self.assertEqual(annotation["annotation_level"], "failure")

    def test_finding_outside_changed_files_gets_no_annotation(self):
        result = _result(findings=[{"file": "other.py", "line": 1, "title": "x"}])
        self.assertEqual(output.render(result, fail_on_block=True)["annotations"], [])

    def test_annotations_are_capped(self):
        findings = [{"file": "app.py", "line": index, "title": "x"} for index in range(1, 80)]
        annotations = output.render(_result(findings=findings), fail_on_block=True)["annotations"]
        self.assertEqual(len(annotations), output.MAX_ANNOTATIONS)

    def test_annotation_message_drops_control_characters(self):
        result = _result(findings=[{"file": "app.py", "line": 1, "title": "bad\x1b[31m title\x00"}])
        message = output.render(result, fail_on_block=True)["annotations"][0]["message"]
        self.assertNotIn("\x1b", message)
        self.assertNotIn("\x00", message)

    def test_summary_lists_metrics(self):
        summary = output.render(_result(), fail_on_block=True)["summary"]
        for fragment in ("BLOCK", "1200", "300", "12.5", "Chunks: 2"):
            self.assertIn(fragment, summary)

    def test_comment_is_capped(self):
        result = _result(reports=["x" * (output.MAX_COMMENT_CHARS + 10)])
        body = output.render(result, fail_on_block=True)["comment_body"]
        self.assertLessEqual(len(body), output.MAX_COMMENT_CHARS)
        self.assertTrue(body.endswith(output.TRUNCATION_NOTE))

    def test_neutral_conclusion_when_not_gating(self):
        self.assertEqual(output.render(_result(), fail_on_block=False)["conclusion"], "neutral")

    def test_missing_usage_renders_as_unknown(self):
        summary = output.render(_result(usage={"input_tokens": None, "output_tokens": None}),
                                fail_on_block=True)["summary"]
        self.assertIn("unknown", summary)


class CliTest(unittest.TestCase):
    """The CLI writes the rendered JSON the workflow publishes."""

    def test_cli_writes_rendered_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "result.json"
            target = Path(directory) / "rendered.json"
            source.write_text(json.dumps(_result(verdict="APPROVE", findings=[])), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(ENGINE_DIR / "review_output.py"), str(source),
                 "--fail-on-block", "true", "--out", str(target)],
                capture_output=True, text=True, check=False)
            rendered = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(rendered["conclusion"], "success")

    def test_cli_rejects_bad_flag_value(self):
        completed = subprocess.run(
            [sys.executable, str(ENGINE_DIR / "review_output.py"), "missing.json",
             "--fail-on-block", "maybe", "--out", "x.json"],
            capture_output=True, text=True, check=False)
        self.assertNotEqual(completed.returncode, 0)


if __name__ == "__main__":
    unittest.main()

"""Test the euler-style review comment that every persona posts."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
BASE_SHA = "b" * 40
HEAD_SHA = "a" * 40
RUN_URL = "https://github.com/abuzucom/example/actions/runs/1"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


output = _load("review_output")


def _result(**changes) -> dict:
    result = {
        "persona": "euler", "mode": "quality", "base_sha": BASE_SHA, "head_sha": HEAD_SHA,
        "verdict": "APPROVE", "reasons": [], "findings": [], "changed_files": [], "unreviewed": [],
        "chunks": 2, "clamped": [], "usage": {}, "duration_seconds": 1.0,
        "chunk_results": [
            {"name": "001", "verdict": "APPROVE", "report": "First report.\nVERDICT: APPROVE", "reason": ""},
            {"name": "002", "verdict": "APPROVE", "report": "Second report.", "reason": ""},
        ],
        "reports": ["First report.\nVERDICT: APPROVE", "Second report."],
    }
    result.update(changes)
    return result


def _lines(result: dict) -> list[str]:
    return output.render(result, fail_on_block=True, run_url=RUN_URL)["comment_body"].split("\n")


class CommentLayoutTest(unittest.TestCase):
    """The comment shows the verdict in a heading like the euler review."""

    def test_first_line_is_a_hidden_marker(self):
        self.assertEqual(_lines(_result())[0], f"<!-- persona-review: euler / quality | head {HEAD_SHA} -->")

    def test_heading_names_persona_mode_and_verdict(self):
        self.assertIn("## Euler quality review: APPROVE", _lines(_result()))

    def test_revisions_and_run_link_follow_the_heading(self):
        lines = _lines(_result())
        self.assertIn(f"Base `{BASE_SHA}`. Head `{HEAD_SHA}`.", lines)
        self.assertIn(f"Workflow run: {RUN_URL}", lines)

    def test_each_chunk_gets_a_verdict_heading(self):
        lines = _lines(_result())
        self.assertIn("### Chunk 001: APPROVE", lines)
        self.assertIn("### Chunk 002: APPROVE", lines)

    def test_report_sits_inside_a_fence_longer_than_its_backticks(self):
        result = _result(chunk_results=[{"name": "001", "verdict": "BLOCK",
                                          "report": "Has ```` four ticks.", "reason": ""}])
        body = output.render(result, fail_on_block=True, run_url=RUN_URL)["comment_body"]
        self.assertIn("`````\nHas ```` four ticks.\n`````", body)

    def test_chunk_without_report_shows_its_reason(self):
        result = _result(verdict="NEEDS-HUMAN", chunk_results=[
            {"name": "001", "verdict": "NEEDS-HUMAN", "report": "", "reason": "input exceeds every model capacity"}])
        lines = _lines(result)
        self.assertIn("### Chunk 001: NEEDS-HUMAN", lines)
        self.assertIn("input exceeds every model capacity", lines)

    def test_run_reasons_are_listed(self):
        result = _result(verdict="NEEDS-HUMAN", reasons=["1 unreviewed file(s) forbid APPROVE"])
        self.assertIn("- 1 unreviewed file(s) forbid APPROVE", _lines(result))

    def test_missing_run_url_omits_the_link_line(self):
        body = output.render(_result(), fail_on_block=True)["comment_body"]
        self.assertNotIn("Workflow run:", body)

    def test_result_without_chunk_results_uses_reports(self):
        result = _result()
        del result["chunk_results"]
        self.assertIn("### Chunk 001: APPROVE", _lines(result))

    def test_long_comment_stays_under_the_cap(self):
        result = _result(chunk_results=[{"name": f"{index:03d}", "verdict": "APPROVE",
                                          "report": "x" * 20_000, "reason": ""} for index in range(1, 6)])
        body = output.render(result, fail_on_block=True, run_url=RUN_URL)["comment_body"]
        self.assertLessEqual(len(body), output.MAX_COMMENT_CHARS)
        self.assertTrue(body.endswith(output.TRUNCATION_NOTE))


class CliRunUrlTest(unittest.TestCase):
    """The CLI passes --run-url into the comment."""

    def test_cli_accepts_run_url(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "result.json"
            target = Path(directory) / "rendered.json"
            source.write_text(json.dumps(_result()), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(ENGINE_DIR / "review_output.py"), str(source), "--fail-on-block", "true",
                 "--run-url", RUN_URL, "--out", str(target)],
                capture_output=True, text=True, check=False)
            rendered = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(f"Workflow run: {RUN_URL}", rendered["comment_body"])


if __name__ == "__main__":
    unittest.main()

"""Test the stop-requested label.

A pull request with the stop-requested label skips every persona review,
even when a <persona>-scan-requested label is on. Adding the label posts a
notice comment. Removing it reviews the current head with the personas that
apply to it.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CALLERS = {"foucault": "foucault-security-review-pr.yml", "euler": "euler-quality-review-pr.yml"}
NOTICE = "stop-requested-notice.yml"


def _workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _trigger(workflow: dict) -> dict:
    return workflow.get("on", workflow.get(True))


def _path_match(stop: str, scan: str) -> str:
    """Run engine/path_filter.py on a matching file and return paths_match."""
    with tempfile.TemporaryDirectory() as directory:
        changed = Path(directory) / "files.json"
        changed.write_text('["engine/run_review.py"]', encoding="utf-8")
        output = Path(directory) / "output.txt"
        environment = {**os.environ, "PATH_PATTERNS": "", "SCAN_REQUESTED": scan, "STOP_REQUESTED": stop,
                       "GITHUB_OUTPUT": str(output)}
        subprocess.run([sys.executable, str(REPO_ROOT / "engine" / "path_filter.py"), str(changed)],
                       env=environment, check=True, capture_output=True)
        return output.read_text(encoding="utf-8").strip()


class PathFilterStopTest(unittest.TestCase):
    """STOP_REQUESTED=true deselects the pull request over every other input."""

    def test_stop_beats_scan_request(self):
        self.assertEqual(_path_match("true", "true"), "paths_match=false")
        self.assertEqual(_path_match("true", ""), "paths_match=false")

    def test_without_stop_review_runs(self):
        self.assertEqual(_path_match("", ""), "paths_match=true")


class ResolveStopTest(unittest.TestCase):
    """The resolve job reports the stop label and the skip job names it."""

    def setUp(self):
        self.jobs = _workflow("review.yml")["jobs"]
        self.steps = {step["name"]: step for step in self.jobs["resolve"]["steps"]}

    def test_resolve_reports_the_stop_label(self):
        script = self.steps["Resolve pull request"]["with"]["script"]
        self.assertIn('"stop-requested"', script)
        self.assertIn('core.setOutput("stop_requested"', script)
        self.assertEqual(self.jobs["resolve"]["outputs"]["stop_requested"],
                         "${{ steps.pull.outputs.stop_requested }}")
        self.assertEqual(self.steps["Match caller paths"]["env"]["STOP_REQUESTED"],
                         "${{ steps.pull.outputs.stop_requested }}")

    def test_skip_job_publishes_stop(self):
        job = self.jobs["skip-paths"]
        step = job["steps"][0]
        self.assertEqual(step["env"]["STOP_REQUESTED"], "${{ needs.resolve.outputs.stop_requested }}")
        script = step["with"]["script"]
        self.assertIn('conclusion: "skipped"', script)
        self.assertIn("Scans stopped", script)
        self.assertIn("Remove the stop-requested label", script)


class CallerUnlabelTest(unittest.TestCase):
    """Removing stop-requested starts each self-review on the current head."""

    def test_callers_run_stop_label_goes(self):
        for persona, name in CALLERS.items():
            job = _workflow(name)["jobs"][persona]
            with self.subTest(persona=persona):
                self.assertIn("github.event.action == 'unlabeled' && github.event.label.name == 'stop-requested'",
                              " ".join(job["if"].split()))
                self.assertIn("github.event.action == 'labeled' && github.event.label.name == "
                              f"'{persona}-scan-requested'", " ".join(job["if"].split()))


class NoticeWorkflowTest(unittest.TestCase):
    """Adding stop-requested posts one notice comment and nothing else."""

    def setUp(self):
        self.workflow = _workflow(NOTICE)
        self.job = next(iter(self.workflow["jobs"].values()))

    def test_notice_runs_stop_label(self):
        self.assertEqual(_trigger(self.workflow)["pull_request_target"], {"types": ["labeled"]})
        self.assertEqual(self.job["if"], "github.event.label.name == 'stop-requested'")

    def test_notice_holds_least_privilege(self):
        self.assertEqual(self.workflow["permissions"], {})
        self.assertEqual(self.job["permissions"], {"pull-requests": "write"})
        text = (WORKFLOWS / NOTICE).read_text(encoding="utf-8")
        self.assertNotIn("actions/checkout", text)
        self.assertNotIn("secrets.", text)

    def test_notice_tells_how_to_resume(self):
        script = self.job["steps"][0]["with"]["script"]
        self.assertIn("createComment", script)
        self.assertIn("Remove the `stop-requested` label", script)
        self.assertIn("before merge", script)


if __name__ == "__main__":
    unittest.main()

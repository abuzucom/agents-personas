"""Test the <persona>-scan-requested label override.

A pull request that carries the <persona>-scan-requested label reviews with
that persona even when the paths input excludes every changed file. Each
self-review caller also starts when a person adds its label.
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


def _workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _trigger(workflow: dict) -> dict:
    return workflow.get("on", workflow.get(True))


def _path_match(files: str, scan_requested: str) -> str:
    """Run engine/path_filter.py and return its paths_match output."""
    with tempfile.TemporaryDirectory() as directory:
        changed = Path(directory) / "files.json"
        changed.write_text(files, encoding="utf-8")
        output = Path(directory) / "output.txt"
        environment = {
            **os.environ,
            "PATH_PATTERNS": "!CHANGELOG.md\n!README.md",
            "SCAN_REQUESTED": scan_requested,
            "GITHUB_OUTPUT": str(output),
        }
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "engine" / "path_filter.py"), str(changed)],
            env=environment,
            check=True,
            capture_output=True,
        )
        return output.read_text(encoding="utf-8").strip()


class PathFilterOverrideTest(unittest.TestCase):
    """SCAN_REQUESTED=true selects the pull request whatever the paths input says."""

    def test_requested_scan_runs_on_excluded_files(self):
        self.assertEqual(_path_match('["CHANGELOG.md"]', "true"), "paths_match=true")

    def test_without_the_request_excluded_files_skip(self):
        for value in ("", "false"):
            with self.subTest(value=value):
                self.assertEqual(_path_match('["CHANGELOG.md"]', value), "paths_match=false")


class ResolveLabelTest(unittest.TestCase):
    """The resolve job reads the persona label and passes it to the path match."""

    def setUp(self):
        self.job = _workflow("review.yml")["jobs"]["resolve"]
        self.steps = {step["name"]: step for step in self.job["steps"]}

    def test_resolve_step_reports_the_persona_label(self):
        script = self.steps["Resolve pull request"]["with"]["script"]
        self.assertIn("`${env.INPUT_PERSONA}-scan-requested`", script)
        self.assertIn('core.setOutput("scan_requested"', script)
        self.assertEqual(self.job["outputs"]["scan_requested"], "${{ steps.pull.outputs.scan_requested }}")

    def test_path_match_receives_the_request(self):
        step = self.steps["Match caller paths"]
        self.assertEqual(step["env"]["SCAN_REQUESTED"], "${{ steps.pull.outputs.scan_requested }}")

    def test_skipped_check_names_the_label(self):
        script = _workflow("review.yml")["jobs"]["skip-paths"]["steps"][0]["with"]["script"]
        self.assertIn("-scan-requested", script)


class CallerTriggerTest(unittest.TestCase):
    """Adding the persona label starts that self-review from the default branch."""

    def test_each_caller_listens_for_its_label(self):
        for persona, name in CALLERS.items():
            workflow = _workflow(name)
            job = workflow["jobs"][persona]
            with self.subTest(persona=persona):
                # The active human approved unlabeled for the stop-requested label.
                self.assertEqual(_trigger(workflow)["pull_request_target"], {"types": ["labeled", "unlabeled"]})
                self.assertIn(f"github.event.label.name == '{persona}-scan-requested'", job["if"])
                self.assertIn("github.event_name == 'pull_request_target'", job["if"])
                self.assertIn("github.event.workflow_run.event == 'pull_request'", job["if"])

    def test_concurrency_group_names_the_head_for_both_triggers(self):
        for persona, name in CALLERS.items():
            group = _workflow(name)["jobs"][persona]["concurrency"]["group"]
            with self.subTest(caller=name):
                self.assertIn("github.event.workflow_run.head_sha", group)
                self.assertIn("github.event.pull_request.head.sha", group)


if __name__ == "__main__":
    unittest.main()

"""Test .github/workflows/eval-live.yml.

A person adds the eval-live label. The workflow grades each changed persona
of the pull request against the live model, once per case, in every mode.
The engine, the grader, and the workflow come from the default branch. The
pull request's persona files reach the run as staged data only.
"""
import re
import unittest
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "eval-live.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _steps(job: dict) -> dict[str, dict]:
    return {step["name"]: step for step in job["steps"]}


class TriggerTest(unittest.TestCase):
    """Only a person adding eval-live starts a run, and only for same-repository heads."""

    def test_label_add_starts_the_run(self):
        workflow = _workflow()
        self.assertEqual(workflow.get("on", workflow.get(True)), {"pull_request_target": {"types": ["labeled"]}})
        self.assertEqual(workflow["permissions"], {})
        select = workflow["jobs"]["select"]
        self.assertIn("github.event.label.name == 'eval-live'", select["if"])
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", select["if"])

    def test_select_lists_changed_personas_only(self):
        select = _workflow()["jobs"]["select"]
        self.assertEqual(select["permissions"], {"pull-requests": "read"})
        script = _steps(select)["List changed personas"]["with"]["script"]
        for fragment in ("listFiles", "^reviewers\\/([a-z][a-z0-9-]{0,31})\\/", 'file.status !== "removed"',
                         'core.setOutput("personas"'):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, script)


class EvalJobTest(unittest.TestCase):
    """The eval job stages data, grades with trusted code, and publishes a check."""

    def setUp(self):
        self.job = _workflow()["jobs"]["eval"]
        self.steps = _steps(self.job)

    def test_job_holds_least_privilege(self):
        self.assertEqual(self.job["permissions"], {"checks": "write", "contents": "read"})
        # A hung provider ends the run. The check step still publishes a failure.
        self.assertEqual(self.job["timeout-minutes"], 60)
        self.assertEqual(self.job["strategy"]["matrix"]["persona"], "${{ fromJSON(needs.select.outputs.personas) }}")

    def test_checkouts_persist_no_credential(self):
        checkouts = [step for step in self.job["steps"] if step.get("uses", "").startswith("actions/checkout@")]
        self.assertEqual(len(checkouts), 2)
        for step in checkouts:
            with self.subTest(step=step["name"]):
                self.assertIs(step["with"]["persist-credentials"], False)
        head = self.steps["Check out the pull request personas"]["with"]
        self.assertEqual((head["ref"], head["path"]), ("${{ github.event.pull_request.head.sha }}", ".pr-head"))

    def test_pull_request_files_reach_only_the_staging_step(self):
        for name, step in self.steps.items():
            if name in ("Check out the pull request personas", "Stage the persona data"):
                continue
            with self.subTest(step=name):
                self.assertNotIn(".pr-head", yaml.safe_dump(step))
        self.assertIn("engine/stage_persona.py --source .pr-head", self.steps["Stage the persona data"]["run"])

    def test_eval_uses_the_trusted_grader_and_the_staged_data(self):
        run = self.steps["Run the live eval"]["run"]
        for fragment in ('--root "$RUNNER_TEMP/eval-root"', "--extension-root .",
                         "--model-call engine.call_model:call_model", "--max-cases 150"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, run)
        # Every mode runs once. --model-call shares the --mode prefix, so the
        # check needs a word boundary.
        self.assertIsNone(re.search(r"--repeat\b|--mode\b", run))

    def test_only_the_eval_step_holds_the_key(self):
        for name, step in self.steps.items():
            holds_key = "secrets." in yaml.safe_dump(step)
            with self.subTest(step=name):
                self.assertEqual(holds_key, name == "Run the live eval")
        self.assertEqual(self.steps["Run the live eval"]["env"]["MODEL_API_KEY"], "${{ secrets.OLLAMA_API_KEY }}")

    def test_check_run_reports_every_outcome(self):
        step = self.steps["Publish the eval check"]
        self.assertEqual(step["if"], "${{ always() }}")
        script = step["with"]["script"]
        self.assertIn("`eval-live / ${process.env.PERSONA}`", script)
        self.assertIn("head_sha: process.env.HEAD_SHA", script)
        self.assertEqual(step["env"]["HEAD_SHA"], "${{ github.event.pull_request.head.sha }}")


if __name__ == "__main__":
    unittest.main()

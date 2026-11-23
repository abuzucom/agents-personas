"""Test that persona scans requested together run together.

GitHub sends a labeled event to every self-review caller. A caller whose
persona label did not change skips its job. A workflow-level concurrency
group still enrolled that skipped run and cancelled the running review of
its persona. Each caller therefore holds the group on its review job. A
skipped job joins no group.

A review that a newer run replaces ends as cancelled. It publishes no check
run. The newer run owns the check. A cancelled run therefore cannot land a
stale check after the newer verdict.
"""

import unittest
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
CALLERS = {
    "adorno": "adorno-ui-review-pr.yml",
    "euler": "euler-quality-review-pr.yml",
    "foucault": "foucault-security-review-pr.yml",
    "generay": "generay-time-review-pr.yml",
}
HEAD_EXPRESSIONS = ("github.event.workflow_run.head_sha", "github.event.pull_request.head.sha")


def _workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _review_step(name: str) -> dict:
    steps = _workflow("review.yml")["jobs"]["review"]["steps"]
    return next(step for step in steps if step.get("name") == name)


class CallerConcurrencyTest(unittest.TestCase):
    """Each caller scopes its concurrency group to its review job."""

    def test_no_caller_holds_a_workflow_level_group(self):
        for persona, name in CALLERS.items():
            with self.subTest(caller=persona):
                self.assertNotIn("concurrency", _workflow(name))

    def test_review_job_holds_a_per_persona_head_group(self):
        for persona, name in CALLERS.items():
            concurrency = _workflow(name)["jobs"][persona]["concurrency"]
            with self.subTest(caller=persona):
                self.assertTrue(concurrency["group"].startswith(f"{persona}-"))
                for expression in HEAD_EXPRESSIONS:
                    self.assertIn(expression, concurrency["group"])
                self.assertIs(concurrency["cancel-in-progress"], True)

    def test_groups_differ_between_personas(self):
        groups = [_workflow(name)["jobs"][persona]["concurrency"]["group"] for persona, name in CALLERS.items()]
        self.assertEqual(len(set(groups)), len(groups))


class CancelledReviewTest(unittest.TestCase):
    """A cancelled review publishes no check and reports no failure."""

    def test_check_run_step_skips_a_cancelled_job(self):
        condition = _review_step("Publish check run")["if"]
        self.assertIn("!cancelled()", condition)
        self.assertIn("steps.cached.outputs.hit != 'true'", condition)

    def test_check_run_script_holds_no_cancelled_branch(self):
        step = _review_step("Publish check run")
        self.assertNotIn("cancelled", step["with"]["script"])
        self.assertNotIn("JOB_STATUS", step.get("env", {}))

    def test_gate_step_skips_a_cancelled_job(self):
        self.assertIn("!cancelled()", _review_step("Fail on a gating verdict")["if"])


if __name__ == "__main__":
    unittest.main()

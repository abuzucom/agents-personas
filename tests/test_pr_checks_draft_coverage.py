#!/usr/bin/env python3
"""Require the blocking pr-checks job to run on draft pull requests.

Rule 5 makes every agent pull request a draft. A pr-checks job gated on
ready status never runs check_agent_prose_gate.py during the working life
of an agent pull request.
"""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REUSABLE_WORKFLOW = ROOT / ".github" / "workflows" / "agents-compliance.yml"
PR_CHECKS_JOB = "pr-checks"
AGENT_PROSE_GATE = "python scripts/check_agent_prose_gate.py"


def load_pr_checks_job() -> dict:
    """Return the parsed pr-checks job of the reusable compliance workflow."""
    workflow = yaml.safe_load(REUSABLE_WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"][PR_CHECKS_JOB]


class PrChecksDraftCoverageTest(unittest.TestCase):
    """Keep the agent prose gate active while a pull request is a draft."""

    def test_pr_checks_condition_ignores_draft_state(self):
        condition = load_pr_checks_job().get("if", "")
        self.assertNotIn("draft", condition)

    def test_pr_checks_still_limits_itself_to_pull_requests(self):
        condition = load_pr_checks_job().get("if", "")
        self.assertIn("github.event_name == 'pull_request'", condition)

    def test_pr_checks_runs_the_agent_prose_gate(self):
        steps = load_pr_checks_job()["steps"]
        commands = [step.get("run", "") for step in steps]
        self.assertTrue(any(AGENT_PROSE_GATE in command for command in commands))


if __name__ == "__main__":
    unittest.main()

"""Test the self-review caller gates and the yamllint coverage of persona workflows.

A workflow_run review starts only after a successful Convention Sync Check.
A failed or cancelled sync run calls no model. Each caller lock names the
pull request as well as the persona and the head. Two pull requests on one
head commit then never cancel each other. make lint-code lints every persona
wrapper and every self-review caller.
"""

import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CALLERS = {
    "adorno": "adorno-ui-review-pr.yml",
    "euler": "euler-quality-review-pr.yml",
    "foucault": "foucault-security-review-pr.yml",
    "generay": "generay-time-review-pr.yml",
    "havel": "havel-privacy-review-pr.yml",
}
SUCCESS_CONDITION = (
    "github.event_name == 'workflow_run' && github.event.workflow_run.event == 'pull_request' && "
    "github.event.workflow_run.conclusion == 'success'"
)
PULL_REQUEST_EXPRESSIONS = (
    "github.event.pull_request.number",
    "github.event.workflow_run.pull_requests[0].number",
)
HEAD_EXPRESSIONS = ("github.event.workflow_run.head_sha", "github.event.pull_request.head.sha")
YAML_PATHS_PATTERN = re.compile(r"^YAML_PATHS = (.*?)(?:\n\n|\Z)", re.MULTILINE | re.DOTALL)


def _job(persona: str) -> dict:
    workflow = yaml.safe_load((WORKFLOWS / CALLERS[persona]).read_text(encoding="utf-8"))
    return workflow["jobs"][persona]


class SuccessGateTest(unittest.TestCase):
    """A workflow_run review needs a successful Convention Sync Check."""

    def test_caller_requires_successful_sync_run(self):
        for persona in CALLERS:
            with self.subTest(caller=persona):
                condition = " ".join(_job(persona)["if"].split())
                self.assertIn(SUCCESS_CONDITION, condition)

    def test_label_branches_ignore_sync(self):
        for persona in CALLERS:
            with self.subTest(caller=persona):
                condition = " ".join(_job(persona)["if"].split())
                label_branches = condition.split(") ||", 1)[1]
                self.assertNotIn("workflow_run.conclusion", label_branches)


class PullRequestLockTest(unittest.TestCase):
    """Each caller lock names the pull request, the persona, and the head."""

    def test_lock_names_pull_request_triggers(self):
        for persona in CALLERS:
            group = _job(persona)["concurrency"]["group"]
            with self.subTest(caller=persona):
                for expression in PULL_REQUEST_EXPRESSIONS + HEAD_EXPRESSIONS:
                    self.assertIn(expression, group)

    def test_fork_runs_use_head(self):
        for persona in CALLERS:
            with self.subTest(caller=persona):
                self.assertIn("github.event.workflow_run.head_branch", _job(persona)["concurrency"]["group"])


class YamlLintCoverageTest(unittest.TestCase):
    """make lint-code lints every persona wrapper and self-review caller."""

    def test_yaml_paths_name_persona_workflow(self):
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        listed = set(YAML_PATHS_PATTERN.search(makefile).group(1).replace("\\\n", " ").split())
        persona_workflows = {
            f".github/workflows/{path.name}"
            for path in WORKFLOWS.glob("*-review*.yml")
            if path.name != "review.yml" and path.name.split("-")[0] in CALLERS
        }
        self.assertEqual(len(persona_workflows), 2 * len(CALLERS))
        self.assertLessEqual(persona_workflows, listed)


if __name__ == "__main__":
    unittest.main()

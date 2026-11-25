"""Test the security and contract properties of .github/workflows/review.yml.

The workflow runs a model over pull request content with a provider secret
in scope. These checks pin the properties that keep that safe: exact action
pins, no persisted checkout credential, no checkout of the pull request
head, a secret-free fork path, and no expression expansion inside scripts.
"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "review.yml"
# Decision 22 in docs/plans/consolidation.md.
APPROVED_PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "6d4fd22b20465ccc0f7354476588e8df7c9ca0e0",
    "actions/github-script": "3a2844b7e9c422d3c10d287c895573f7108da1b3",
    "actions/upload-artifact": "cf430e030ddbb5b0abf93d22962f4752f3646cd9",
}
REQUIRED_INPUTS = {"personas_ref", "persona"}
OPTIONAL_INPUTS = {
    "modes", "pr_number", "base_sha", "head_sha", "head_repo_url", "head_repo_full_name",
    "model_call_command", "pr_comment", "fail_on_block", "fork_review", "max_chunks",
    "max_envelope_bytes", "paths", "persona_options",
}
REVIEW_JOBS = ("review", "fork-review")
EXPRESSION = re.compile(r"\$\{\{")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _trigger(workflow: dict) -> dict:
    # PyYAML reads the bare key "on" as the boolean True.
    return workflow.get("on", workflow.get(True))["workflow_call"]


def _steps(workflow: dict):
    for job_name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            yield job_name, step


class ContractTest(unittest.TestCase):
    """The reusable workflow exposes the planned inputs and one secret."""

    def test_required_and_optional_inputs(self):
        inputs = _trigger(_workflow())["inputs"]
        self.assertEqual({name for name, spec in inputs.items() if spec.get("required")}, REQUIRED_INPUTS)
        self.assertEqual(set(inputs) - REQUIRED_INPUTS, OPTIONAL_INPUTS)

    def test_gating_defaults_match_source_workflows(self):
        inputs = _trigger(_workflow())["inputs"]
        self.assertIs(inputs["fail_on_block"]["default"], True)
        self.assertIs(inputs["pr_comment"]["default"], True)
        self.assertIs(inputs["fork_review"]["default"], False)

    def test_model_api_key_declared_optional(self):
        secrets = _trigger(_workflow())["secrets"]
        self.assertEqual(set(secrets), {"MODEL_API_KEY"})
        self.assertIs(secrets["MODEL_API_KEY"]["required"], False)


class PinTest(unittest.TestCase):
    """Every action uses the approved full-SHA pin."""

    def test_action_uses_approved_pin(self):
        for job_name, step in _steps(_workflow()):
            uses = step.get("uses")
            if not uses:
                continue
            with self.subTest(job=job_name, step=step.get("name")):
                action, _, sha = uses.partition("@")
                self.assertIn(action, APPROVED_PINS)
                self.assertEqual(sha, APPROVED_PINS[action])

    def test_repository_pin_checker_passes(self):
        result = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "check_action_pins.py")],
                                cwd=REPO_ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class CheckoutTest(unittest.TestCase):
    """No checkout persists a credential or checks out the pull request head."""

    def checkouts(self):
        return [(job, step) for job, step in _steps(_workflow())
                if step.get("uses", "").startswith("actions/checkout@")]

    def test_every_checkout_disables_credential_persistence(self):
        for job_name, step in self.checkouts():
            with self.subTest(job=job_name, step=step.get("name")):
                self.assertIs(step["with"]["persist-credentials"], False)

    def test_checkout_avoids_pr_head(self):
        for job_name, step in self.checkouts():
            with self.subTest(job=job_name, step=step.get("name")):
                ref = str(step["with"].get("ref", ""))
                self.assertNotIn("head", ref)

    def test_persist_credentials_checker_passes(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "check_persist_credentials.py"), str(WORKFLOW_PATH)],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ForkRuleTest(unittest.TestCase):
    """A fork receives a skipped check and no secret unless fork_review opts in."""

    def test_skip_job_references_no_secret(self):
        job = _workflow()["jobs"]["skip-fork"]
        self.assertNotIn("secrets.", yaml.safe_dump(job))
        self.assertIn("fork", str(job["if"]))

    def test_skip_job_reports_skipped_checks(self):
        text = yaml.safe_dump(_workflow()["jobs"]["skip-fork"])
        self.assertIn("skipped", text)
        self.assertIn("Skipped for fork pull request", text)

    def test_fork_job_uses_protected_environment(self):
        jobs = _workflow()["jobs"]
        self.assertEqual(jobs["fork-review"]["environment"], "fork-review")
        self.assertNotIn("environment", jobs["review"])

    def test_review_jobs_share_steps(self):
        jobs = _workflow()["jobs"]
        self.assertEqual(jobs["review"]["steps"], jobs["fork-review"]["steps"])

    def test_review_job_skips_forks(self):
        condition = str(_workflow()["jobs"]["review"]["if"])
        self.assertIn("same_repository", condition)
        self.assertIn("fork_review", condition)


class SecretScopeTest(unittest.TestCase):
    """The provider key and the token each reach exactly one step."""

    def steps_referencing(self, marker: str) -> set:
        names = set()
        for job_name, step in _steps(_workflow()):
            if job_name in REVIEW_JOBS and marker in yaml.safe_dump(step):
                names.add(step["name"])
        return names

    def test_api_key_reaches_review(self):
        self.assertEqual(self.steps_referencing("secrets.MODEL_API_KEY"), {"Run review"})

    def test_token_reaches_head_fetch(self):
        self.assertEqual(self.steps_referencing("github.token"), {"Fetch pull request head object"})


class NeedsHumanWarningTest(unittest.TestCase):
    """The review jobs emit the rendered NEEDS-HUMAN warning on the run."""

    def test_gate_step_emits_rendered_warning(self):
        steps = {step["name"]: step for job, step in _steps(_workflow()) if job == "review"}
        body = steps["Fail on a gating verdict"]["run"]
        self.assertIn("::warning", body)
        self.assertIn('rendered["warning"]', body)

    def test_fail_block_input_names_block(self):
        description = _trigger(_workflow())["inputs"]["fail_on_block"]["description"]
        self.assertIn("BLOCK", description)
        self.assertIn("NEEDS-HUMAN warns", description)


class CommentLayoutWiringTest(unittest.TestCase):
    """The workflow posts the renderer's comment and matches its hidden marker."""

    def review_steps(self) -> dict:
        return {step["name"]: step for job, step in _steps(_workflow()) if job == "review"}

    def test_render_step_passes_run_url(self):
        step = self.review_steps()["Render review output"]
        self.assertIn("--run-url", step["run"])
        self.assertIn("RUN_URL", step["env"])

    def test_comment_step_posts_rendered_body(self):
        script = self.review_steps()["Post review comment"]["with"]["script"]
        self.assertIn("body: rendered.comment_body", script)

    def test_comment_lookup_matches_marker(self):
        resolve = {step["name"]: step for job, step in _steps(_workflow()) if job == "resolve"}
        script = resolve["Find earlier review comments"]["with"]["script"]
        self.assertIn("<!-- persona-review: ", script)


class ScriptInjectionTest(unittest.TestCase):
    """Scripts read values from env. No expression expands inside a script body."""

    def test_run_lacks_expressions(self):
        for job_name, step in _steps(_workflow()):
            body = step.get("run") or step.get("with", {}).get("script", "")
            with self.subTest(job=job_name, step=step.get("name")):
                self.assertIsNone(EXPRESSION.search(body))


if __name__ == "__main__":
    unittest.main()

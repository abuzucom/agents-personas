"""Pin the trust boundary of .github/workflows/review.yml for privileged callers.

A pull_request_target caller relies on engine properties alone. These checks
fail when a later engine change checks out the pull request head, widens the
provider key scope, or drops the same_repository_only guard.
"""
import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
ENGINE_PATH = WORKFLOWS / "review.yml"
WRAPPER_PATHS = tuple(WORKFLOWS / name for name in (
    "adorno-ui-review.yml",
    "euler-quality-review.yml",
    "foucault-security-review.yml",
    "generay-time-review.yml",
    "havel-privacy-review.yml",
))
GUARD_INPUT = "same_repository_only"
GUARD_ENV = "INPUT_SAME_REPOSITORY_ONLY"
KEY_STEP = "Run review"
SECRET_REFERENCE = re.compile(r"secrets\.MODEL_API_KEY")
HEAD_REFERENCE = re.compile(r"head_sha|head_repo|pull_request\.head", re.IGNORECASE)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _inputs(workflow: dict) -> dict:
    # PyYAML reads the bare key "on" as the boolean True.
    return workflow.get("on", workflow.get(True))["workflow_call"]["inputs"]


def _resolve_step(workflow: dict) -> dict:
    return next(step for step in workflow["jobs"]["resolve"]["steps"] if step.get("id") == "pull")


class GuardInputTest(unittest.TestCase):
    """same_repository_only stays optional and off by default."""

    def test_guard_input_defaults_false(self):
        for path in (ENGINE_PATH, *WRAPPER_PATHS):
            with self.subTest(workflow=path.name):
                spec = _inputs(_load(path))[GUARD_INPUT]
                self.assertIs(spec.get("required"), False)
                self.assertEqual(spec["type"], "boolean")
                self.assertIs(spec["default"], False)

    def test_wrappers_forward_guard_input(self):
        for path in WRAPPER_PATHS:
            with self.subTest(workflow=path.name):
                call = _load(path)["jobs"]["review"]["with"]
                self.assertEqual(call[GUARD_INPUT], "${{ inputs.same_repository_only }}")


class GuardResolveTest(unittest.TestCase):
    """The resolve job fails closed on a fork head before any secret job."""

    def test_resolve_receives_guard_input(self):
        step = _resolve_step(_load(ENGINE_PATH))
        self.assertEqual(step["env"][GUARD_ENV], "${{ inputs.same_repository_only }}")

    def test_resolve_throws_on_fork(self):
        script = _resolve_step(_load(ENGINE_PATH))["with"]["script"]
        guard = re.search(r"if \(env\.INPUT_SAME_REPOSITORY_ONLY === \"true\" && !sameRepository\) \{\s*"
                          r"throw new Error\(", script)
        self.assertIsNotNone(guard, "the resolve script must throw on a fork head under the guard")
        # The guard runs before the job publishes any output.
        self.assertLess(guard.start(), script.index("core.setOutput("))

    def test_resolve_holds_no_secret(self):
        job = _load(ENGINE_PATH)["jobs"]["resolve"]
        self.assertIsNone(SECRET_REFERENCE.search(yaml.safe_dump(job)))

    def test_secret_jobs_need_resolve(self):
        for job_name, job in _load(ENGINE_PATH)["jobs"].items():
            if not SECRET_REFERENCE.search(yaml.safe_dump(job)):
                continue
            with self.subTest(job=job_name):
                self.assertIn("resolve", [job["needs"]] if isinstance(job["needs"], str) else job["needs"])


class TrustBoundaryTest(unittest.TestCase):
    """No checkout names the head, and the key reaches one step only."""

    def test_checkout_avoids_head_repository(self):
        for job_name, job in _load(ENGINE_PATH)["jobs"].items():
            for step in job.get("steps", []):
                if not step.get("uses", "").startswith("actions/checkout@"):
                    continue
                with self.subTest(job=job_name, step=step.get("name")):
                    self.assertIsNone(HEAD_REFERENCE.search(yaml.safe_dump(step.get("with", {}))))

    def test_model_key_in_run_step(self):
        for job_name, job in _load(ENGINE_PATH)["jobs"].items():
            for step in job.get("steps", []):
                if not SECRET_REFERENCE.search(yaml.safe_dump(step)):
                    continue
                with self.subTest(job=job_name, step=step.get("name")):
                    self.assertEqual(step.get("name"), KEY_STEP)
                    self.assertEqual(set(step["env"]) & {"MODEL_API_KEY"}, {"MODEL_API_KEY"})
                    self.assertNotIn("MODEL_API_KEY", yaml.safe_dump(step.get("with", {})))

    def test_jobs_hold_no_secret_env(self):
        for job_name, job in _load(ENGINE_PATH)["jobs"].items():
            with self.subTest(job=job_name):
                self.assertIsNone(SECRET_REFERENCE.search(yaml.safe_dump(job.get("env", {}))))


if __name__ == "__main__":
    unittest.main()

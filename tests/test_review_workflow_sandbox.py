"""Test the hook sandbox wiring in .github/workflows/review.yml.

The review jobs run on a pinned Ubuntu image, install the pinned bubblewrap,
and require the sandbox in both stage steps. A missing sandbox then fails
the run closed.
"""
import unittest
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "review.yml"
REVIEW_JOBS = ("review", "fork-review")
# Approved under Rule 9 on 2026-11-20. noble-updates and noble-security carry this build.
BUBBLEWRAP_INSTALL = "sudo apt-get install -y --no-install-recommends bubblewrap=0.9.0-1ubuntu0.3"
STAGE_STEPS = ("Build review case", "Run review")


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"]


def _steps(job: str) -> list[dict]:
    return _jobs()[job]["steps"]


class SandboxWiringTest(unittest.TestCase):
    """Each review job installs bubblewrap and requires it in both stage steps."""

    def test_review_jobs_run_pinned_image(self):
        for job in REVIEW_JOBS:
            with self.subTest(job=job):
                self.assertEqual(_jobs()[job]["runs-on"], "ubuntu-24.04")

    def test_install_pins_bubblewrap(self):
        for job in REVIEW_JOBS:
            names = [step["name"] for step in _steps(job)]
            with self.subTest(job=job):
                install = next(step for step in _steps(job) if step["name"] == "Install bubblewrap")
                self.assertIn(BUBBLEWRAP_INSTALL, install["run"])
                self.assertNotIn("secrets.", yaml.safe_dump(install))
                self.assertLess(names.index("Install bubblewrap"), names.index("Build review case"))

    def test_stage_steps_require_the_sandbox(self):
        for job in REVIEW_JOBS:
            steps = {step["name"]: step for step in _steps(job)}
            for name in STAGE_STEPS:
                with self.subTest(job=job, step=name):
                    self.assertEqual(steps[name]["env"]["PERSONAS_REQUIRE_SANDBOX"], "1")

    def test_no_step_turns_sandbox_off(self):
        self.assertNotIn("PERSONAS_REQUIRE_SANDBOX: off", WORKFLOW_PATH.read_text(encoding="utf-8"))
        self.assertNotIn("PERSONAS_REQUIRE_SANDBOX: \"off\"", WORKFLOW_PATH.read_text(encoding="utf-8"))


SANDBOX_CHECK_PATH = WORKFLOW_PATH.with_name("sandbox-check.yml")
SANDBOX_TESTS = "tests.test_engine_hook_sandbox tests.test_engine_key_exposure tests.test_euler_review_hooks"


class SandboxCheckWorkflowTest(unittest.TestCase):
    """A pull request job proves the sandbox starts on the pinned runner image before merge."""

    def setUp(self):
        self.workflow = yaml.safe_load(SANDBOX_CHECK_PATH.read_text(encoding="utf-8"))
        self.job = self.workflow["jobs"]["sandbox"]

    def test_job_reads_pull_requests(self):
        trigger = self.workflow.get("on", self.workflow.get(True))
        self.assertIn("pull_request", trigger)
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertEqual(self.job["runs-on"], "ubuntu-24.04")

    def test_job_installs_pinned_bubblewrap_requires(self):
        steps = {step["name"]: step for step in self.job["steps"]}
        self.assertIn(BUBBLEWRAP_INSTALL, steps["Install bubblewrap"]["run"])
        run = steps["Run sandbox tests"]
        self.assertEqual(run["env"]["PERSONAS_REQUIRE_SANDBOX"], "1")
        self.assertIn(SANDBOX_TESTS, run["run"])

    def test_checkout_persists_no_credential(self):
        checkout = next(step for step in self.job["steps"] if step.get("uses", "").startswith("actions/checkout@"))
        self.assertIs(checkout["with"]["persist-credentials"], False)


PROFILE_PATH = WORKFLOW_PATH.parent.parent.parent / "engine" / "apparmor" / "bwrap"
PROFILE_LOAD = "sudo apparmor_parser -r /etc/apparmor.d/bwrap"


class AppArmorProfileTest(unittest.TestCase):
    """Ubuntu 24.04 restricts unprivileged user namespaces. One profile lets bwrap alone create them."""

    def test_profile_grants_userns_bwrap(self):
        text = PROFILE_PATH.read_text(encoding="ascii")
        self.assertIn("profile bwrap /usr/bin/bwrap flags=(unconfined) {", text)
        self.assertIn("  userns,", text)
        rules = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
        self.assertEqual(rules, ["abi <abi/4.0>,", "include <tunables/global>",
                                 "profile bwrap /usr/bin/bwrap flags=(unconfined) {", "userns,",
                                 "include if exists <local/bwrap>", "}"])

    def test_review_jobs_load_profile(self):
        for job in REVIEW_JOBS:
            install = next(step for step in _steps(job) if step["name"] == "Install bubblewrap")
            with self.subTest(job=job):
                self.assertIn("sudo install -m 0644 .agents-personas/engine/apparmor/bwrap /etc/apparmor.d/bwrap",
                              install["run"])
                self.assertIn(PROFILE_LOAD, install["run"])

    def test_sandbox_check_loads_repository_profile(self):
        workflow = yaml.safe_load(SANDBOX_CHECK_PATH.read_text(encoding="utf-8"))
        install = next(step for step in workflow["jobs"]["sandbox"]["steps"] if step["name"] == "Install bubblewrap")
        self.assertIn("sudo install -m 0644 engine/apparmor/bwrap /etc/apparmor.d/bwrap", install["run"])
        self.assertIn(PROFILE_LOAD, install["run"])


if __name__ == "__main__":
    unittest.main()

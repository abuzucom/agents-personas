"""Test the foucault wrapper, the self-review caller, and the caller examples."""
import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WRAPPER = WORKFLOWS / "foucault-security-review.yml"
SELF_CALLER = WORKFLOWS / "foucault-security-review-pr.yml"
ENGINE = WORKFLOWS / "review.yml"
EXAMPLES = REPO_ROOT / "examples"
SHA = re.compile(r"^[0-9a-f]{40}$")
FORWARDED_INPUTS = {"personas_ref", "modes", "pr_number", "base_sha", "head_sha", "head_repo_url",
                    "head_repo_full_name", "model_call_command", "pr_comment", "fail_on_block",
                    "fork_review", "paths"}
REVIEW_PERMISSIONS = {"checks": "write", "contents": "read", "pull-requests": "write"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _trigger(workflow: dict) -> dict:
    # PyYAML reads the bare key "on" as the boolean True.
    return workflow.get("on", workflow.get(True))


class WrapperTest(unittest.TestCase):
    """The wrapper fixes persona and mode and forwards every caller input."""

    def setUp(self):
        self.workflow = _load(WRAPPER)
        self.call = _trigger(self.workflow)["workflow_call"]
        self.job = self.workflow["jobs"]["review"]

    def test_wrapper_inputs_are_the_engine_inputs_minus_persona_and_caps(self):
        engine_inputs = _trigger(_load(ENGINE))["workflow_call"]["inputs"]
        self.assertEqual(set(self.call["inputs"]), FORWARDED_INPUTS)
        for name in FORWARDED_INPUTS:
            with self.subTest(input=name):
                self.assertEqual(self.call["inputs"][name].get("required", False),
                                 engine_inputs[name].get("required", False))
                self.assertEqual(self.call["inputs"][name]["type"], engine_inputs[name]["type"])

    def test_wrapper_calls_the_engine_for_foucault_with_the_default_mode(self):
        self.assertEqual(self.job["uses"], "./.github/workflows/review.yml")
        self.assertEqual(self.job["with"]["persona"], "foucault")
        self.assertEqual(self.call["inputs"]["modes"]["default"], "")

    def test_wrapper_forwards_every_input_by_name(self):
        for name in FORWARDED_INPUTS:
            with self.subTest(input=name):
                self.assertEqual(self.job["with"][name], f"${{{{ inputs.{name} }}}}")

    def test_wrapper_passes_only_the_model_key(self):
        self.assertEqual(set(self.call["secrets"]), {"MODEL_API_KEY"})
        self.assertIs(self.call["secrets"]["MODEL_API_KEY"]["required"], False)
        self.assertEqual(self.job["secrets"], {"MODEL_API_KEY": "${{ secrets.MODEL_API_KEY }}"})

    def test_wrapper_grants_the_engine_permissions(self):
        self.assertEqual(self.job["permissions"], REVIEW_PERMISSIONS)
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})


class SelfCallerTest(unittest.TestCase):
    """The repository reviews its own pull requests after the sync check."""

    def setUp(self):
        self.workflow = _load(SELF_CALLER)
        self.job = self.workflow["jobs"]["foucault"]

    def test_caller_runs_after_the_sync_check(self):
        run = _trigger(self.workflow)["workflow_run"]
        self.assertEqual(run, {"workflows": ["Convention Sync Check"], "types": ["completed"]})

    def test_caller_uses_the_default_branch_engine(self):
        self.assertEqual(self.job["uses"], "./.github/workflows/foucault-security-review.yml")
        self.assertEqual(self.job["with"]["personas_ref"], "${{ github.sha }}")

    def test_caller_maps_the_ollama_key_only(self):
        self.assertEqual(self.job["secrets"], {"MODEL_API_KEY": "${{ secrets.OLLAMA_API_KEY }}"})
        self.assertNotIn("inherit", str(self.workflow))

    def test_caller_skips_runs_that_did_not_come_from_a_pull_request(self):
        self.assertIn("github.event.workflow_run.event == 'pull_request'", self.job["if"])


class ExampleCallerTest(unittest.TestCase):
    """The adopter examples pin the engine by full SHA and gate optional personas by label."""

    def jobs(self, name: str) -> dict:
        return _load(EXAMPLES / name)["jobs"]

    def test_examples_pin_uses_and_personas_ref_to_one_sha(self):
        for name in ("always-on-caller.yml", "label-caller.yml"):
            for job_name, job in self.jobs(name).items():
                with self.subTest(example=name, job=job_name):
                    reference, _, sha = job["uses"].partition("@")
                    self.assertTrue(reference.startswith("abuzucom/agents-personas/.github/workflows/"))
                    self.assertRegex(sha, SHA)
                    self.assertEqual(job["with"]["personas_ref"], sha)
                    self.assertEqual(set(job["secrets"]), {"MODEL_API_KEY"})

    def test_always_on_example_runs_foucault_and_euler_after_ci(self):
        workflow = _load(EXAMPLES / "always-on-caller.yml")
        self.assertIn("workflow_run", _trigger(workflow))
        self.assertEqual(set(workflow["jobs"]), {"foucault", "euler"})

    def test_label_example_gates_each_job_on_its_label(self):
        workflow = _load(EXAMPLES / "label-caller.yml")
        trigger = _trigger(workflow)["pull_request_target"]
        self.assertEqual(trigger["types"], ["labeled", "synchronize"])
        labels = {"adorno": "review:adorno", "generay": "review:generay",
                  "generay-sync": "review:generay-sync", "havel": "review:havel"}
        self.assertEqual(set(workflow["jobs"]), set(labels))
        for job_name, label in labels.items():
            with self.subTest(job=job_name):
                self.assertIn(f"'{label}'", workflow["jobs"][job_name]["if"])
        self.assertEqual(workflow["jobs"]["generay-sync"]["with"]["modes"], "sync")


if __name__ == "__main__":
    unittest.main()

"""Test the generay wrapper and the label-only generay self-review caller."""

import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WRAPPER = WORKFLOWS / "generay-time-review.yml"
SELF_CALLER = WORKFLOWS / "generay-time-review-pr.yml"
ENGINE = WORKFLOWS / "review.yml"
FORWARDED_INPUTS = {
    "personas_ref",
    "modes",
    "pr_number",
    "base_sha",
    "head_sha",
    "head_repo_url",
    "head_repo_full_name",
    "model_call_command",
    "pr_comment",
    "fail_on_block",
    "fork_review",
    "paths",
}
GENERAY_INPUTS = {"exclude_paths", "max_chunks"}
REVIEW_PERMISSIONS = {"checks": "write", "contents": "read", "pull-requests": "write"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _trigger(workflow: dict) -> dict:
    # PyYAML reads the bare key "on" as the boolean True.
    return workflow.get("on", workflow.get(True))


class WrapperTest(unittest.TestCase):
    """The wrapper fixes the persona, forwards engine inputs, and requires the key."""

    def setUp(self):
        self.workflow = _load(WRAPPER)
        self.call = _trigger(self.workflow)["workflow_call"]
        self.job = self.workflow["jobs"]["review"]

    def test_wrapper_declares_engine_generay_inputs(self):
        self.assertEqual(set(self.call["inputs"]), FORWARDED_INPUTS | GENERAY_INPUTS)
        engine_inputs = _trigger(_load(ENGINE))["workflow_call"]["inputs"]
        for name in FORWARDED_INPUTS:
            with self.subTest(input=name):
                self.assertEqual(self.call["inputs"][name]["type"], engine_inputs[name]["type"])

    def test_generay_inputs_keep_types(self):
        inputs = self.call["inputs"]
        self.assertEqual((inputs["exclude_paths"]["type"], inputs["exclude_paths"]["default"]), ("string", ""))
        self.assertEqual((inputs["max_chunks"]["type"], inputs["max_chunks"]["default"]), ("number", 20))

    def test_wrapper_forwards_engine_input_name(self):
        self.assertEqual(self.job["uses"], "./.github/workflows/review.yml")
        self.assertEqual(self.job["with"]["persona"], "generay")
        for name in FORWARDED_INPUTS:
            with self.subTest(input=name):
                self.assertEqual(self.job["with"][name], f"${{{{ inputs.{name} }}}}")

    def test_exclude_max_chunks_reach_engine(self):
        self.assertIn("toJSON(inputs.exclude_paths)", self.job["with"]["persona_options"])
        self.assertEqual(self.job["with"]["max_chunks"], "${{ format('{0}', inputs.max_chunks) }}")

    def test_wrapper_requires_model_key(self):
        self.assertEqual(set(self.call["secrets"]), {"MODEL_API_KEY"})
        self.assertIs(self.call["secrets"]["MODEL_API_KEY"]["required"], True)
        self.assertEqual(self.job["secrets"], {"MODEL_API_KEY": "${{ secrets.MODEL_API_KEY }}"})

    def test_wrapper_grants_the_engine_permissions(self):
        self.assertEqual(self.job["permissions"], REVIEW_PERMISSIONS)
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})


class SelfCallerTest(unittest.TestCase):
    """This repository reviews with generay only when a person adds its label."""

    def setUp(self):
        self.workflow = _load(SELF_CALLER)
        self.job = self.workflow["jobs"]["generay"]

    def test_label_alone_runs_excluded_review(self):
        self.assertEqual(self.job["with"]["paths"].split(), ["!**"])

    def test_caller_starts_ci_completion_labels(self):
        trigger = _trigger(self.workflow)
        self.assertEqual(trigger["workflow_run"], {"workflows": ["Convention Sync Check"], "types": ["completed"]})
        self.assertEqual(trigger["pull_request_target"], {"types": ["labeled", "unlabeled"]})
        condition = " ".join(self.job["if"].split())
        self.assertIn("github.event.label.name == 'generay-scan-requested'", condition)
        self.assertIn("github.event.action == 'unlabeled' && github.event.label.name == 'stop-requested'", condition)

    def test_caller_uses_default_engine_key(self):
        self.assertEqual(self.job["uses"], "./.github/workflows/generay-time-review.yml")
        self.assertEqual(self.job["with"]["personas_ref"], "${{ github.sha }}")
        self.assertEqual(self.job["secrets"], {"MODEL_API_KEY": "${{ secrets.OLLAMA_API_KEY }}"})
        self.assertEqual(self.job["permissions"], REVIEW_PERMISSIONS)


if __name__ == "__main__":
    unittest.main()

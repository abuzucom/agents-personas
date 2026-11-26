"""Test the adorno wrapper and the label-only adorno self-review caller."""

import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WRAPPER = WORKFLOWS / "adorno-ui-review.yml"
SELF_CALLER = WORKFLOWS / "adorno-ui-review-pr.yml"
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
    "same_repository_only",
    "paths",
}
REVIEW_PERMISSIONS = {"checks": "write", "contents": "read", "pull-requests": "write"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _trigger(workflow: dict) -> dict:
    # PyYAML reads the bare key "on" as the boolean True.
    return workflow.get("on", workflow.get(True))


class WrapperTest(unittest.TestCase):
    """The wrapper fixes the persona, forwards engine inputs, and keeps the key optional."""

    def setUp(self):
        self.workflow = _load(WRAPPER)
        self.call = _trigger(self.workflow)["workflow_call"]
        self.job = self.workflow["jobs"]["review"]

    def test_wrapper_declares_engine_input_types(self):
        self.assertEqual(set(self.call["inputs"]), FORWARDED_INPUTS)
        engine_inputs = _trigger(_load(ENGINE))["workflow_call"]["inputs"]
        for name in FORWARDED_INPUTS:
            with self.subTest(input=name):
                self.assertEqual(self.call["inputs"][name]["type"], engine_inputs[name]["type"])

    def test_wrapper_forwards_input_fixes_persona(self):
        self.assertEqual(self.job["uses"], "./.github/workflows/review.yml")
        self.assertEqual(self.job["with"]["persona"], "adorno")
        for name in FORWARDED_INPUTS:
            with self.subTest(input=name):
                self.assertEqual(self.job["with"][name], f"${{{{ inputs.{name} }}}}")

    def test_wrapper_keeps_model_key_optional(self):
        self.assertEqual(set(self.call["secrets"]), {"MODEL_API_KEY"})
        self.assertIs(self.call["secrets"]["MODEL_API_KEY"]["required"], False)
        self.assertEqual(self.job["secrets"], {"MODEL_API_KEY": "${{ secrets.MODEL_API_KEY }}"})

    def test_wrapper_grants_the_engine_permissions(self):
        self.assertEqual(self.job["permissions"], REVIEW_PERMISSIONS)
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})


class SelfCallerTest(unittest.TestCase):
    """This repository reviews with adorno only when a person adds its label."""

    def setUp(self):
        self.workflow = _load(SELF_CALLER)
        self.job = self.workflow["jobs"]["adorno"]

    def test_label_alone_runs_excluded_review(self):
        self.assertEqual(self.job["with"]["paths"].split(), ["!**"])

    def test_caller_passes_inputs_wrapper_declares(self):
        declared = set(_trigger(_load(WRAPPER))["workflow_call"]["inputs"])
        self.assertLessEqual(set(self.job["with"]), declared)

    def test_caller_starts_ci_completion_labels(self):
        trigger = _trigger(self.workflow)
        self.assertEqual(trigger["workflow_run"], {"workflows": ["Convention Sync Check"], "types": ["completed"]})
        self.assertEqual(trigger["pull_request_target"], {"types": ["labeled", "unlabeled"]})
        condition = " ".join(self.job["if"].split())
        self.assertIn("github.event.label.name == 'adorno-scan-requested'", condition)
        self.assertIn("github.event.action == 'unlabeled' && github.event.label.name == 'stop-requested'", condition)

    def test_caller_uses_default_engine_key(self):
        self.assertEqual(self.job["uses"], "./.github/workflows/adorno-ui-review.yml")
        self.assertEqual(self.job["with"]["personas_ref"], "${{ github.sha }}")
        self.assertEqual(self.job["secrets"], {"MODEL_API_KEY": "${{ secrets.OLLAMA_API_KEY }}"})
        self.assertEqual(self.job["permissions"], REVIEW_PERMISSIONS)


if __name__ == "__main__":
    unittest.main()

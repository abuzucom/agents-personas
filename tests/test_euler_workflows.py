"""Test the euler wrapper and the euler self-review caller."""

import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WRAPPER = WORKFLOWS / "euler-quality-review.yml"
SELF_CALLER = WORKFLOWS / "euler-quality-review-pr.yml"
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
EULER_INPUTS = {"exclude_paths", "max_chunks"}
REVIEW_PERMISSIONS = {"checks": "write", "contents": "read", "pull-requests": "write"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _trigger(workflow: dict) -> dict:
    # PyYAML reads the bare key "on" as the boolean True.
    return workflow.get("on", workflow.get(True))


class WrapperTest(unittest.TestCase):
    """The wrapper fixes the persona, forwards engine inputs, and maps euler inputs."""

    def setUp(self):
        self.workflow = _load(WRAPPER)
        self.call = _trigger(self.workflow)["workflow_call"]
        self.job = self.workflow["jobs"]["review"]

    def test_wrapper_declares_engine_euler_inputs(self):
        self.assertEqual(set(self.call["inputs"]), FORWARDED_INPUTS | EULER_INPUTS)
        engine_inputs = _trigger(_load(ENGINE))["workflow_call"]["inputs"]
        for name in FORWARDED_INPUTS:
            with self.subTest(input=name):
                self.assertEqual(self.call["inputs"][name]["type"], engine_inputs[name]["type"])
                self.assertEqual(
                    self.call["inputs"][name].get("required", False), engine_inputs[name].get("required", False)
                )

    def test_euler_inputs_keep_types(self):
        inputs = self.call["inputs"]
        self.assertEqual((inputs["exclude_paths"]["type"], inputs["exclude_paths"]["default"]), ("string", ""))
        self.assertEqual((inputs["max_chunks"]["type"], inputs["max_chunks"]["default"]), ("number", 20))

    def test_wrapper_forwards_engine_input_name(self):
        self.assertEqual(self.job["uses"], "./.github/workflows/review.yml")
        self.assertEqual(self.job["with"]["persona"], "euler")
        for name in FORWARDED_INPUTS:
            with self.subTest(input=name):
                self.assertEqual(self.job["with"][name], f"${{{{ inputs.{name} }}}}")

    def test_exclude_paths_reaches_engine(self):
        value = self.job["with"]["persona_options"]
        self.assertIn("exclude_paths", value)
        self.assertIn("toJSON(inputs.exclude_paths)", value)

    def test_max_chunks_reaches_engine_cap(self):
        self.assertEqual(self.job["with"]["max_chunks"], "${{ format('{0}', inputs.max_chunks) }}")

    def test_wrapper_passes_model_key(self):
        self.assertEqual(set(self.call["secrets"]), {"MODEL_API_KEY"})
        self.assertIs(self.call["secrets"]["MODEL_API_KEY"]["required"], False)
        self.assertEqual(self.job["secrets"], {"MODEL_API_KEY": "${{ secrets.MODEL_API_KEY }}"})

    def test_wrapper_grants_the_engine_permissions(self):
        self.assertEqual(self.job["permissions"], REVIEW_PERMISSIONS)
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})


class SelfCallerTest(unittest.TestCase):
    """euler reviews this repository after the sync check and skips tests/ in the prescan."""

    def setUp(self):
        self.workflow = _load(SELF_CALLER)
        self.job = self.workflow["jobs"]["euler"]

    def test_caller_runs_after_sync_check(self):
        run = _trigger(self.workflow)["workflow_run"]
        self.assertEqual(run, {"workflows": ["Convention Sync Check"], "types": ["completed"]})

    def test_caller_uses_default_branch_engine(self):
        self.assertEqual(self.job["uses"], "./.github/workflows/euler-quality-review.yml")
        self.assertEqual(self.job["with"]["personas_ref"], "${{ github.sha }}")
        self.assertIn("github.event.workflow_run.event == 'pull_request'", self.job["if"])

    def test_caller_excludes_fixtures_prescan(self):
        # Test files and eval cases hold flagged patterns on purpose.
        self.assertEqual(self.job["with"]["exclude_paths"].split(), ["tests/**", "reviewers/*/eval/cases/**"])

    def test_caller_maps_ollama_key(self):
        self.assertEqual(self.job["secrets"], {"MODEL_API_KEY": "${{ secrets.OLLAMA_API_KEY }}"})


if __name__ == "__main__":
    unittest.main()

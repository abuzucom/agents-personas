"""Test the build and review stages and persona_options in .github/workflows/review.yml."""
import unittest
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "review.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _review_steps(job: str = "review") -> list[dict]:
    return _workflow()["jobs"][job]["steps"]


def _step(name: str, job: str = "review") -> dict:
    return next(step for step in _review_steps(job) if step["name"] == name)


class PersonaOptionsInputTest(unittest.TestCase):
    """persona_options is optional and empty by default."""

    def test_input_defaults_to_empty(self):
        inputs = _workflow().get("on", _workflow().get(True))["workflow_call"]["inputs"]
        self.assertFalse(inputs["persona_options"].get("required", False))
        self.assertEqual(inputs["persona_options"]["default"], "")
        self.assertEqual(inputs["persona_options"]["type"], "string")


class StageTest(unittest.TestCase):
    """The build stage runs persona hooks before the provider key enters the job."""

    def test_build_step_precedes_the_review_step(self):
        names = [step["name"] for step in _review_steps()]
        self.assertLess(names.index("Build review case"), names.index("Run review"))

    def test_build_step_holds_no_secret_and_runs_the_build_stage(self):
        step = _step("Build review case")
        self.assertNotIn("secrets.", yaml.safe_dump(step))
        self.assertIn("--stage build", step["run"])
        self.assertEqual(step["env"]["PERSONA_OPTIONS"], "${{ inputs.persona_options }}")

    def test_review_step_reads_the_built_case(self):
        step = _step("Run review")
        self.assertIn("--stage review", step["run"])
        # The review stage checks the options digest against the built case.
        self.assertEqual(step["env"]["PERSONA_OPTIONS"], "${{ inputs.persona_options }}")

    def test_persona_options_reach_only_the_two_stage_steps(self):
        for job in ("review", "fork-review"):
            names = {step["name"] for step in _review_steps(job) if "persona_options" in yaml.safe_dump(step)}
            with self.subTest(job=job):
                # The key step hashes the options so a changed option set never reuses a
                # cached verdict. The active human approved this entry.
                self.assertEqual(names, {"Compute review key", "Build review case", "Run review"})


if __name__ == "__main__":
    unittest.main()

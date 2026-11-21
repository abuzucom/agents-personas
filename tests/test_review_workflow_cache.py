"""Test the one-review-per-head cache wiring in .github/workflows/review.yml.

Each review job computes the review key, then looks for a completed check
run from the github-actions app on the same head, name, and key. On a match
the job reuses that conclusion and skips every step that fetches the head,
builds the case, or calls the model. A published check run carries the key
in its external_id.
"""
import unittest
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "review.yml"
REVIEW_JOBS = ("review", "fork-review")
HIT = "steps.cached.outputs.hit != 'true'"
SKIPPED_ON_HIT = ("Fetch pull request head object", "Install bubblewrap", "Build review case", "Run review",
                  "Publish check run")


def _steps(job: str) -> list[dict]:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"][job]["steps"]


def _named(job: str) -> dict[str, dict]:
    return {step["name"]: step for step in _steps(job)}


class CacheWiringTest(unittest.TestCase):
    """Both review jobs compute the key and look up an earlier check run first."""

    def test_key_and_lookup_run_before_the_head_fetch(self):
        for job in REVIEW_JOBS:
            names = [step["name"] for step in _steps(job)]
            with self.subTest(job=job):
                self.assertLess(names.index("Set up Python"), names.index("Compute review key"))
                self.assertLess(names.index("Compute review key"), names.index("Find an earlier review"))
                self.assertLess(names.index("Find an earlier review"), names.index("Fetch pull request head object"))

    def test_key_step_passes_every_key_field(self):
        step = _named("review")["Compute review key"]
        self.assertEqual(step["id"], "key")
        self.assertIn("engine/review_key.py", step["run"])
        self.assertEqual(set(step["env"]), {"PERSONA", "MODE", "HEAD_SHA", "BASE_SHA", "PERSONAS_REF", "PR_TITLE",
                                            "PR_BODY", "PERSONA_OPTIONS", "MAX_CHUNKS", "MAX_ENVELOPE_BYTES",
                                            "MODEL_CALL_COMMAND", "FAIL_ON_BLOCK"})
        self.assertEqual(step["env"]["PERSONAS_REF"], "${{ inputs.personas_ref }}")
        self.assertEqual(step["env"]["MODEL_CALL_COMMAND"], "${{ inputs.model_call_command }}")
        self.assertEqual(step["env"]["FAIL_ON_BLOCK"], "${{ inputs.fail_on_block }}")
        self.assertNotIn("secrets.", yaml.safe_dump(step))

    def test_lookup_matches_app_status_name_and_key(self):
        step = _named("review")["Find an earlier review"]
        self.assertEqual(step["id"], "cached")
        script = step["with"]["script"]
        for fragment in ("listForRef", 'filter: "all"', '"github-actions"', 'status === "completed"',
                         "external_id === process.env.REVIEW_KEY", 'core.setOutput("hit"',
                         'core.setOutput("conclusion"'):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, script)
        self.assertEqual(step["env"]["REVIEW_KEY"], "${{ steps.key.outputs.key }}")

    def test_hit_skips_the_fetch_build_model_and_publish_steps(self):
        for job in REVIEW_JOBS:
            steps = _named(job)
            for name in SKIPPED_ON_HIT:
                with self.subTest(job=job, step=name):
                    self.assertIn(HIT, str(steps[name].get("if", "")))

    def test_published_check_run_carries_the_key(self):
        step = _named("review")["Publish check run"]
        self.assertIn("external_id: process.env.REVIEW_KEY", step["with"]["script"])
        self.assertEqual(step["env"]["REVIEW_KEY"], "${{ steps.key.outputs.key }}")

    def test_failure_check_run_carries_no_key(self):
        script = _named("review")["Publish check run"]["with"]["script"]
        failure = script[script.index("Review failed before a verdict") - 300:]
        self.assertNotIn("external_id", failure[:400])

    def test_gate_step_fails_a_reused_failure(self):
        step = _named("review")["Fail on a gating verdict"]
        self.assertEqual(step["env"]["CACHED_HIT"], "${{ steps.cached.outputs.hit }}")
        self.assertEqual(step["env"]["CACHED_CONCLUSION"], "${{ steps.cached.outputs.conclusion }}")
        self.assertIn('os.environ.get("CACHED_HIT") == "true"', step["run"])


if __name__ == "__main__":
    unittest.main()

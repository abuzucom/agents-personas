"""Test the paths input wiring in .github/workflows/review.yml."""
import unittest
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "review.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _inputs(workflow: dict) -> dict:
    return workflow.get("on", workflow.get(True))["workflow_call"]["inputs"]


class PathsInputTest(unittest.TestCase):
    """paths is optional and empty by default, which keeps every run."""

    def test_paths_input_defaults_to_empty(self):
        spec = _inputs(_workflow())["paths"]
        self.assertFalse(spec.get("required", False))
        self.assertEqual(spec["default"], "")

    def test_resolve_job_outputs_paths_match(self):
        self.assertIn("paths_match", _workflow()["jobs"]["resolve"]["outputs"])


class PathsSkipTest(unittest.TestCase):
    """No matching file posts a skipped check and runs no review."""

    def test_skip_job_posts_no_matching_files_without_secret(self):
        job = _workflow()["jobs"]["skip-paths"]
        text = yaml.safe_dump(job)
        self.assertIn("paths_match", str(job["if"]))
        self.assertIn("No matching files", text)
        self.assertIn("skipped", text)
        self.assertNotIn("secrets.", text)

    def test_review_jobs_require_a_path_match(self):
        jobs = _workflow()["jobs"]
        for name in ("review", "fork-review", "skip-fork"):
            with self.subTest(job=name):
                self.assertIn("paths_match == 'true'", str(jobs[name]["if"]))


if __name__ == "__main__":
    unittest.main()

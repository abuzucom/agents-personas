"""Test the tag-triggered draft wiring in .github/workflows/release.yml."""

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
TOOL = "python tools/release_personas.py"
FULL_SHA_PIN = re.compile(r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")
ATTEST_ACTION = "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6"
WRITE_PERMISSIONS = {"contents": "write", "id-token": "write", "attestations": "write"}


def load_workflow() -> dict:
    """Return the parsed release workflow."""
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def load_triggers() -> dict:
    """Return the on block, which YAML 1.1 can parse as the key True."""
    workflow = load_workflow()
    return workflow.get("on", workflow.get(True))


def list_steps(job: str) -> list[dict]:
    """Return the steps of one job."""
    return load_workflow()["jobs"][job]["steps"]


def collect_runs(job: str) -> str:
    """Return every run script of one job joined by newlines."""
    return "\n".join(step.get("run", "") for step in list_steps(job))


class TriggerTest(unittest.TestCase):
    """Only a pushed v tag starts the workflow."""

    def test_trigger_is_v_tags(self):
        self.assertEqual(load_triggers(), {"push": {"tags": ["v*"]}})

    def test_top_permissions_read_only(self):
        self.assertEqual(load_workflow()["permissions"], {"contents": "read"})

    def test_concurrency_never_cancels(self):
        concurrency = load_workflow()["concurrency"]
        self.assertFalse(concurrency["cancel-in-progress"])
        self.assertIn("github.ref", concurrency["group"])


class CheckTagJobTest(unittest.TestCase):
    """check-tag checks the version and the main ancestry."""

    def test_job_runs_tool_check(self):
        self.assertIn(f'{TOOL} check-tag "$GITHUB_REF_NAME"', collect_runs("check-tag"))

    def test_job_checks_main_ancestry(self):
        self.assertIn('git merge-base --is-ancestor "$GITHUB_SHA" origin/main', collect_runs("check-tag"))

    def test_checkout_fetches_full_history(self):
        checkout = list_steps("check-tag")[0]
        self.assertEqual(checkout["with"]["fetch-depth"], 0)

    def test_job_has_no_write(self):
        self.assertNotIn("permissions", load_workflow()["jobs"]["check-tag"])


class DraftJobTest(unittest.TestCase):
    """The release job writes only after check-tag and the environment approval."""

    def setUp(self):
        self.job = load_workflow()["jobs"]["release"]
        self.runs = collect_runs("release")

    def test_job_needs_check_tag(self):
        self.assertEqual(self.job["needs"], "check-tag")

    def test_job_uses_release_environment(self):
        self.assertEqual(self.job["environment"], "release")

    def test_job_permissions_exact(self):
        self.assertEqual(self.job["permissions"], WRITE_PERMISSIONS)

    def test_job_builds_and_checks_archive(self):
        self.assertIn(f"{TOOL} archive", self.runs)
        self.assertIn(f"{TOOL} check-assets", self.runs)
        self.assertIn("--require-bundles", self.runs)

    def test_job_writes_sums_and_notes(self):
        self.assertIn(f"{TOOL} checksums", self.runs)
        self.assertIn(f'{TOOL} notes "${{GITHUB_REF_NAME#v}}" "$GITHUB_SHA"', self.runs)

    def test_attest_covers_archive_and_sums(self):
        subjects = [
            step["with"]["subject-path"] for step in self.job["steps"] if step.get("uses", "").startswith(ATTEST_ACTION)
        ]
        self.assertEqual(len(subjects), 2)
        self.assertTrue(any(subject.endswith(".tar.gz") for subject in subjects))
        self.assertTrue(any(subject.endswith("SHA256SUMS.txt") for subject in subjects))

    def test_draft_created_never_published(self):
        self.assertIn("gh release create", self.runs)
        self.assertIn("--draft --verify-tag", self.runs)
        self.assertNotIn("gh release edit", self.runs)
        self.assertNotIn("--draft=false", self.runs)

    def test_published_release_stops_job(self):
        self.assertIn("This job only fills drafts.", self.runs)

    def test_changed_asset_stops_job(self):
        self.assertIn("Delete the draft, then run the tag build again.", self.runs)

    def test_reused_bundle_gets_verified(self):
        self.assertIn("gh attestation verify", self.runs)


class PinTest(unittest.TestCase):
    """Every action carries a full commit SHA and checkout drops credentials."""

    def test_every_action_full_sha(self):
        for job in load_workflow()["jobs"].values():
            for step in job["steps"]:
                if "uses" in step:
                    with self.subTest(uses=step["uses"]):
                        self.assertRegex(step["uses"], FULL_SHA_PIN)

    def test_checkout_drops_credentials(self):
        for job in load_workflow()["jobs"].values():
            for step in job["steps"]:
                if step.get("uses", "").startswith("actions/checkout@"):
                    self.assertIs(step["with"]["persist-credentials"], False)

    def test_no_expression_inside_run(self):
        for job_name in load_workflow()["jobs"]:
            with self.subTest(job=job_name):
                self.assertNotIn("${{", collect_runs(job_name))


if __name__ == "__main__":
    unittest.main()

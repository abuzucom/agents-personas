"""Test the release notes range, usage block, and draft refresh for agents-personas.

The tool runs against a real fixture Git repository with real tags. The
workflow checks read .github/workflows/release.yml.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TOOL_PATH = ROOT / "tools" / "release_personas.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
TOOL = "python tools/release_personas.py"
VERSION = "1.2.3"
REPOSITORY = "abuzucom/agents-personas"
SIGNER = f"{REPOSITORY}/.github/workflows/release.yml"
CHANGELOG_TEXT = """# Changelog

Intro text.

## [1.2.3] (2026-11-25)

### Added
- Add the newest feature.

## [1.2.2] (2026-11-24)

### Fixed
- Fix the middle bug.

## [1.2.1] (2026-11-23)

### Fixed
- Fix the oldest bug.
"""


def run_git(repository: Path, *arguments: str) -> str:
    """Run one Git command in a fixture repository and return its output."""
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            *arguments,
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def run_tool(root: Path, *arguments: str) -> subprocess.CompletedProcess:
    """Run the tool as a process from a fixture root."""
    return subprocess.run(
        [sys.executable, str(TOOL_PATH), "--root", str(root), *arguments], capture_output=True, text=True, check=False
    )


class TaggedRepositoryFixture(unittest.TestCase):
    """A fixture Git repository with a three-version changelog."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repository"
        self.root.mkdir()
        run_git(self.root, "init", "-q", "-b", "main")
        run_git(self.root, "config", "maintenance.auto", "false")
        (self.root / "CHANGELOG.md").write_text(CHANGELOG_TEXT, encoding="utf-8")
        run_git(self.root, "add", "-A")
        run_git(self.root, "commit", "-q", "-m", "fixture")
        self.head = run_git(self.root, "rev-parse", "HEAD")

    def tag(self, *names: str) -> None:
        """Create one lightweight tag per name on the fixture head."""
        for name in names:
            run_git(self.root, "tag", name)

    def write_notes(self) -> str:
        """Run the notes subcommand and return the notes text."""
        path = Path(self.temporary.name) / "notes.md"
        result = run_tool(self.root, "notes", VERSION, self.head, str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return path.read_text(encoding="utf-8")


class PreviousTagTest(TaggedRepositoryFixture):
    """previous-tag prints the highest stable tag below the version."""

    def test_previous_tag_skips_others(self):
        self.tag("v1.0.0", "v1.2.1", "v1.2.2-rc.1", "v1.2.3", "v2.0.0", "release", "v01.2.2")
        result = run_tool(self.root, "previous-tag", VERSION)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "v1.2.1")

    def test_previous_tag_empty_without_tags(self):
        result = run_tool(self.root, "previous-tag", VERSION)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_previous_tag_rejects_bad_version(self):
        self.assertEqual(run_tool(self.root, "previous-tag", "1.2").returncode, 1)


class NotesRangeTest(TaggedRepositoryFixture):
    """notes holds every section newer than the previous stable tag."""

    def test_notes_keep_version_headings(self):
        self.tag("v1.2.1")
        notes = self.write_notes()
        self.assertIn("## [1.2.3] (2026-11-25)", notes)
        self.assertIn("## [1.2.2] (2026-11-24)", notes)
        self.assertIn("- Fix the middle bug.", notes)
        self.assertNotIn("## [1.2.1]", notes)
        self.assertNotIn("- Fix the oldest bug.", notes)
        self.assertNotIn("Intro text.", notes)

    def test_notes_without_tags_hold_all(self):
        notes = self.write_notes()
        self.assertIn("- Fix the oldest bug.", notes)
        self.assertNotIn("Intro text.", notes)

    def test_notes_order_newest_first(self):
        notes = self.write_notes()
        self.assertLess(notes.index("## [1.2.3]"), notes.index("## [1.2.2]"))
        self.assertLess(notes.index("## [1.2.2]"), notes.index("## [1.2.1]"))


class UsageBlockTest(TaggedRepositoryFixture):
    """notes ends with the fixed Using this version block."""

    def test_usage_block_follows_changelog(self):
        notes = self.write_notes()
        self.assertLess(notes.index("- Add the newest feature."), notes.index("## Using this version"))

    def test_usage_pins_name_version(self):
        notes = self.write_notes()
        self.assertIn(f"foucault-security-review.yml@{self.head}  # v{VERSION}", notes)
        self.assertIn(f'personas_ref: "{self.head}"  # v{VERSION}', notes)

    def test_usage_block_verifies_assets(self):
        notes = self.write_notes()
        self.assertIn("sha256sum --check SHA256SUMS.txt", notes)
        self.assertIn(
            f"gh attestation verify agents-personas-{VERSION}.tar.gz --repo {REPOSITORY} --signer-workflow {SIGNER}",
            notes,
        )
        self.assertIn(f"gh attestation verify SHA256SUMS.txt --repo {REPOSITORY} --signer-workflow {SIGNER}", notes)


def release_job() -> dict:
    """Return the parsed release job."""
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"]["release"]


def release_runs() -> str:
    """Return every run script of the release job joined by newlines."""
    return "\n".join(step.get("run", "") for step in release_job()["steps"])


class NotesWorkflowTest(unittest.TestCase):
    """The release job appends generated notes and refreshes a draft."""

    def test_checkout_fetches_tags(self):
        checkout = release_job()["steps"][0]
        self.assertEqual(checkout["with"]["fetch-depth"], 0)

    def test_generated_notes_follow_tool(self):
        runs = release_runs()
        self.assertIn(f'{TOOL} previous-tag "${{GITHUB_REF_NAME#v}}"', runs)
        self.assertIn('"repos/$repo/releases/generate-notes"', runs)
        self.assertLess(runs.index(f"{TOOL} notes"), runs.index("releases/generate-notes"))

    def test_rerun_refreshes_draft_notes(self):
        runs = release_runs()
        self.assertIn(
            'gh release edit "$tag" --repo "$repo" --draft --notes-file "$RUNNER_TEMP/release-notes.md"', runs
        )


if __name__ == "__main__":
    unittest.main()

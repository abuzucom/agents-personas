"""Test tools/release_personas.py against real files and a real Git repository."""

import gzip
import hashlib
import importlib.util
import io
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL_PATH = ROOT / "tools" / "release_personas.py"
VERSION = "1.2.3"
TAG = "v1.2.3"
COMMIT_SHA_LENGTH = 40
CHANGELOG_TEXT = """# Changelog

Intro text.

## [1.2.3] (2026-11-25)

### Added
- Add the feature.

## [1.2.2] (2026-11-24)

### Fixed
- Fix the bug.
"""


def load_tool():
    """Return the tool module loaded from its file path."""
    spec = importlib.util.spec_from_file_location("release_personas", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL = load_tool()


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


class RepositoryFixture(unittest.TestCase):
    """A fixture Git repository with a changelog and one committed file."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repository"
        self.root.mkdir()
        run_git(self.root, "init", "-q", "-b", "main")
        run_git(self.root, "config", "maintenance.auto", "false")
        run_git(self.root, "config", "gc.auto", "0")
        (self.root / "CHANGELOG.md").write_text(CHANGELOG_TEXT, encoding="utf-8")
        (self.root / "engine").mkdir()
        (self.root / "engine" / "tool.py").write_text("VALUE = 1\n", encoding="utf-8")
        run_git(self.root, "add", "-A")
        run_git(self.root, "commit", "-q", "-m", "fixture")
        self.head = run_git(self.root, "rev-parse", "HEAD")

    def make_folder(self, name: str) -> Path:
        """Return a new empty folder inside the fixture directory."""
        folder = Path(self.temporary.name) / name
        folder.mkdir()
        return folder


class CheckTagTest(RepositoryFixture):
    """check-tag compares the tag with the top changelog version."""

    def test_matching_tag_passes(self):
        result = run_tool(self.root, "check-tag", TAG)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_older_tag_fails(self):
        result = run_tool(self.root, "check-tag", "v1.2.2")
        self.assertEqual(result.returncode, 1)
        self.assertIn("1.2.3", result.stdout + result.stderr)

    def test_tag_without_prefix_fails(self):
        result = run_tool(self.root, "check-tag", VERSION)
        self.assertEqual(result.returncode, 1)

    def test_malformed_version_fails(self):
        for tag in ("v1.2", "v01.2.3", "v1.2.3-rc.1", "v1.2.3;x"):
            with self.subTest(tag=tag):
                self.assertEqual(run_tool(self.root, "check-tag", tag).returncode, 1)

    def test_missing_changelog_fails(self):
        (self.root / "CHANGELOG.md").unlink()
        self.assertEqual(run_tool(self.root, "check-tag", TAG).returncode, 1)


class ArchiveTest(RepositoryFixture):
    """archive writes one deterministic tar.gz of the committed tree."""

    def build(self, folder_name: str) -> Path:
        """Build the archive into a new folder and return the archive path."""
        folder = self.make_folder(folder_name)
        result = run_tool(self.root, "archive", VERSION, str(folder))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return folder / TOOL.archive_name(VERSION)

    def test_archive_holds_committed_tree(self):
        archive = self.build("first")
        with tarfile.open(archive, "r:gz") as bundle:
            names = bundle.getnames()
        prefix = f"agents-personas-{VERSION}/"
        self.assertIn(prefix + "CHANGELOG.md", names)
        self.assertIn(prefix + "engine/tool.py", names)
        # tarfile lists the top folder entry without its trailing slash.
        self.assertTrue(all(name == prefix.rstrip("/") or name.startswith(prefix) for name in names))

    def test_archive_skips_uncommitted_files(self):
        (self.root / "scratch.txt").write_text("local\n", encoding="utf-8")
        archive = self.build("first")
        with tarfile.open(archive, "r:gz") as bundle:
            names = bundle.getnames()
        self.assertNotIn(f"agents-personas-{VERSION}/scratch.txt", names)

    def test_rebuild_gives_identical_bytes(self):
        first = self.build("first").read_bytes()
        second = self.build("second").read_bytes()
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())

    def test_gzip_header_holds_zero_mtime(self):
        archive = self.build("first")
        with gzip.GzipFile(fileobj=io.BytesIO(archive.read_bytes())) as stream:
            stream.read()
            self.assertEqual(stream.mtime, 0)

    def test_nonempty_folder_fails(self):
        folder = self.make_folder("busy")
        (folder / "other.txt").write_text("x\n", encoding="utf-8")
        result = run_tool(self.root, "archive", VERSION, str(folder))
        self.assertEqual(result.returncode, 1)


class CheckAssetsTest(RepositoryFixture):
    """check-assets accepts exactly the expected asset names."""

    def write_assets(self, *names: str) -> Path:
        """Write empty files with the given names into a new folder."""
        folder = self.make_folder("assets")
        for name in names:
            (folder / name).write_bytes(b"x")
        return folder

    def test_archive_alone_passes(self):
        folder = self.write_assets(TOOL.archive_name(VERSION))
        self.assertEqual(run_tool(self.root, "check-assets", str(folder), VERSION).returncode, 0)

    def test_required_bundle_missing_fails(self):
        folder = self.write_assets(TOOL.archive_name(VERSION))
        result = run_tool(self.root, "check-assets", str(folder), VERSION, "--require-bundles")
        self.assertEqual(result.returncode, 1)
        self.assertIn(TOOL.bundle_name(VERSION), result.stdout)

    def test_archive_and_bundle_pass(self):
        folder = self.write_assets(TOOL.archive_name(VERSION), TOOL.bundle_name(VERSION))
        result = run_tool(self.root, "check-assets", str(folder), VERSION, "--require-bundles")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_extra_file_fails(self):
        folder = self.write_assets(TOOL.archive_name(VERSION), "stray.txt")
        result = run_tool(self.root, "check-assets", str(folder), VERSION)
        self.assertEqual(result.returncode, 1)
        self.assertIn("stray.txt", result.stdout)

    def test_missing_archive_fails(self):
        folder = self.write_assets()
        self.assertEqual(run_tool(self.root, "check-assets", str(folder), VERSION).returncode, 1)


class ChecksumsTest(RepositoryFixture):
    """checksums writes SHA256SUMS.txt in the sha256sum format."""

    def test_lines_match_file_digests(self):
        folder = self.make_folder("assets")
        (folder / "b.tar.gz").write_bytes(b"beta")
        (folder / "a.json").write_bytes(b"alpha")
        self.assertEqual(run_tool(self.root, "checksums", str(folder)).returncode, 0)
        lines = (folder / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines()
        expected = [
            f"{hashlib.sha256(b'alpha').hexdigest()}  a.json",
            f"{hashlib.sha256(b'beta').hexdigest()}  b.tar.gz",
        ]
        self.assertEqual(lines, expected)

    def test_rerun_skips_existing_sums(self):
        folder = self.make_folder("assets")
        (folder / "a.json").write_bytes(b"alpha")
        run_tool(self.root, "checksums", str(folder))
        run_tool(self.root, "checksums", str(folder))
        lines = (folder / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines()
        self.assertEqual(len(lines), 1)


class NotesTest(RepositoryFixture):
    """notes writes one changelog section and the caller pin block."""

    def write_notes(self, version: str, sha: str) -> subprocess.CompletedProcess:
        """Run the notes subcommand into a fixture file."""
        self.notes_path = Path(self.temporary.name) / "notes.md"
        return run_tool(self.root, "notes", version, sha, str(self.notes_path))

    def test_notes_hold_section_and_pin(self):
        result = self.write_notes(VERSION, self.head)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        notes = self.notes_path.read_text(encoding="utf-8")
        self.assertIn("- Add the feature.", notes)
        self.assertNotIn("- Fix the bug.", notes)
        self.assertNotIn("## [1.2.3]", notes)
        for wrapper in TOOL.CALLER_WORKFLOWS:
            with self.subTest(wrapper=wrapper):
                self.assertIn(f"abuzucom/agents-personas/.github/workflows/{wrapper}@{self.head}", notes)
        self.assertIn(f'personas_ref: "{self.head}"', notes)

    def test_unknown_version_fails(self):
        self.assertEqual(self.write_notes("9.9.9", self.head).returncode, 1)

    def test_short_sha_fails(self):
        self.assertEqual(self.write_notes(VERSION, self.head[:7]).returncode, 1)

    def test_uppercase_sha_fails(self):
        self.assertEqual(len(self.head), COMMIT_SHA_LENGTH)
        self.assertEqual(self.write_notes(VERSION, self.head.upper()).returncode, 1)


if __name__ == "__main__":
    unittest.main()

"""Test engine/build_pr_case.py against a real temporary git repository.

The builder reads the diff from git objects and never checks out the head.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "engine"
SHA_LENGTH = 40
# Every changed path of the fixture head, as the skeleton lists it.
PATHS = [f"file{i}.py" for i in range(4)] + ["image.bin"]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


envelope = _load("envelope")
builder = _load("build_pr_case")

GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=GIT_ENV)
    return result.stdout.strip()


class RepositoryFixture(unittest.TestCase):
    """Create a base commit and a head commit with text and binary files."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.out = Path(self.temp.name) / "out"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "maintenance.auto", "false")
        (self.repo / "keep.txt").write_text("base\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "base")
        self.base = _git(self.repo, "rev-parse", "HEAD")
        for index in range(4):
            (self.repo / f"file{index}.py").write_text(f"value = {index}\n" * 20, encoding="utf-8")
        (self.repo / "image.bin").write_bytes(bytes(range(256)))
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "head")
        self.head = _git(self.repo, "rev-parse", "HEAD")

    def tearDown(self):
        self.temp.cleanup()

    def build(self, **overrides):
        values = {
            "repo": self.repo,
            "base": self.base,
            "head": self.head,
            "out_dir": self.out,
            "persona": "euler",
            "mode": "quality",
            "title": "Title",
            "body": "Body",
            "pr_number": 9,
            "max_chunks": 20,
            "max_envelope_bytes": 200_000,
        }
        values.update(overrides)
        builder.build(builder.BuildOptions(**values))
        return json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))

    def envelopes(self, manifest):
        return [
            json.loads((self.out / "envelopes" / chunk["envelope"]).read_text(encoding="utf-8"))
            for chunk in manifest["chunks"]
        ]


class BuildPrCaseTest(RepositoryFixture):
    """build() writes chunked envelopes and a manifest of unreviewed files."""

    def test_one_chunk_holds_every_text_file(self):
        manifest = self.build()
        self.assertEqual(len(manifest["chunks"]), 1)
        files = self.envelopes(manifest)[0]["REVIEW_TARGET"]["files"]
        self.assertEqual(sorted(files), [f"file{index}.py" for index in range(4)])

    def test_binary_file_is_unreviewed(self):
        self.assertIn("image.bin", self.build()["unreviewed"])

    def test_small_budget_splits_into_chunks(self):
        skeleton = len(
            envelope.build_envelope(
                "euler",
                "quality",
                {},
                "Title",
                "Body",
                builder.chunk_metadata_bound(self.base, self.head, 9, 20, PATHS),
                changed_files=PATHS,
                unreviewed=PATHS,
            ).encode("utf-8")
        )
        manifest = self.build(max_envelope_bytes=skeleton + 600)
        self.assertGreater(len(manifest["chunks"]), 1)
        for document in self.envelopes(manifest):
            self.assertEqual(document["TRUSTED_CONTEXT"]["mode"], "quality")

    def test_chunks_past_the_limit_become_unreviewed(self):
        skeleton = len(
            envelope.build_envelope(
                "euler",
                "quality",
                {},
                "Title",
                "Body",
                builder.chunk_metadata_bound(self.base, self.head, 9, 1, PATHS),
                changed_files=PATHS,
                unreviewed=PATHS,
            ).encode("utf-8")
        )
        manifest = self.build(max_chunks=1, max_envelope_bytes=skeleton + 600)
        self.assertEqual(len(manifest["chunks"]), 1)
        self.assertTrue(any(path.startswith("file") for path in manifest["unreviewed"]))

    def test_every_envelope_respects_the_byte_budget(self):
        budget = 200_000
        manifest = self.build(max_envelope_bytes=budget)
        for chunk in manifest["chunks"]:
            size = (self.out / "envelopes" / chunk["envelope"]).stat().st_size
            self.assertLessEqual(size, budget)

    def test_short_revision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "full lowercase commit SHA"):
            self.build(base=self.base[:7])

    def test_zero_chunk_limit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "max_chunks"):
            self.build(max_chunks=0)

    def test_head_is_never_checked_out(self):
        self.build()
        self.assertEqual(_git(self.repo, "rev-parse", "HEAD"), self.head)
        self.assertEqual(len(self.head), SHA_LENGTH)

    def test_manifest_records_revisions_and_persona(self):
        manifest = self.build()
        self.assertEqual((manifest["base_sha"], manifest["head_sha"]), (self.base, self.head))
        self.assertEqual((manifest["persona"], manifest["mode"]), ("euler", "quality"))


class CliTest(RepositoryFixture):
    """The CLI validates the persona and mode and applies the mode caps."""

    def run_cli(self, *extra: str):
        root = Path(self.temp.name) / "personas"
        persona_dir = root / "reviewers" / "euler"
        persona_dir.mkdir(parents=True, exist_ok=True)
        (persona_dir / "Q.md").write_text("prompt\n", encoding="ascii")
        manifest = {
            "persona": "euler",
            "function": "quality",
            "modes": {"quality": {"prompt": "Q.md", "review": True, "default": True, "max_chunks": 2}},
        }
        (persona_dir / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
        command = [
            sys.executable,
            str(ENGINE_DIR / "build_pr_case.py"),
            "--root",
            str(root),
            "--repo",
            str(self.repo),
            "--base",
            self.base,
            "--head",
            self.head,
            "--pr-number",
            "9",
            "--out-dir",
            str(self.out),
            *extra,
        ]
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def test_high_request_is_clamped_with_notice(self):
        result = self.run_cli("--persona", "euler", "--mode", "quality", "--max-chunks", "9")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("exceeds the mode cap", result.stderr)
        self.assertTrue((self.out / "manifest.json").is_file())

    def test_unknown_persona_is_refused(self):
        result = self.run_cli("--persona", "nobody", "--mode", "quality")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown persona", result.stderr)

    def test_unknown_mode_is_refused(self):
        result = self.run_cli("--persona", "euler", "--mode", "sync")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown mode", result.stderr)


class PureHelpersTest(unittest.TestCase):
    """The ported chunking helpers keep their euler behavior."""

    def test_pack_chunks_splits_by_budget_and_reports_oversized(self):
        patches = {"a": "x" * 4, "b": "x" * 4, "c": "x" * 20}
        chunks, oversized = builder.pack_chunks(patches, 10)
        self.assertEqual((chunks, oversized), ([["a", "b"]], ["c"]))

    def test_limit_chunks_returns_overflow_files(self):
        self.assertEqual(builder.limit_chunks([["a"], ["b", "c"]], 1), ([["a"]], ["b", "c"]))

    def test_split_raw_and_patches_keeps_paths_with_spaces(self):
        output = b":100644 100644 a b M\0my file.py\0\0diff --git a/my file.py b/my file.py\n+x\n"
        paths, patches = builder.split_raw_and_patches(output)
        self.assertEqual(paths, [b"my file.py"])
        self.assertTrue(patches[0].startswith(b"diff --git"))


if __name__ == "__main__":
    unittest.main()

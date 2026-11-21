"""Test engine/stage_persona.py, the eval-live staging step.

The eval-live workflow reads a pull request's persona files as data while
the provider key is present. Staging copies only regular non-Python files
into a fresh tree. A symlink, a special file, an oversized file, or an
unsafe persona name fails the run. Python never reaches the staged tree.
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"


def _load():
    spec = importlib.util.spec_from_file_location("stage_persona", ENGINE_DIR / "stage_persona.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage_persona = _load()


class StageTest(unittest.TestCase):
    """stage() copies the persona data and refuses anything else."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.source = base / "head"
        self.persona = self.source / "reviewers" / "euler"
        (self.persona / "eval" / "cases" / "quality" / "one").mkdir(parents=True)
        (self.persona / "QUALITY.md").write_text("prompt\n", encoding="utf-8")
        (self.persona / "reviewer.json").write_text("{}\n", encoding="utf-8")
        (self.persona / "eval" / "cases" / "quality" / "one" / "diff.patch").write_text("x\n", encoding="utf-8")
        (self.persona / "eval" / "extra_checks.py").write_text("raise SystemExit(9)\n", encoding="utf-8")
        (self.persona / "review_hooks.py").write_text("raise SystemExit(9)\n", encoding="utf-8")
        self.target = base / "staged"

    def staged(self) -> Path:
        return self.target / "reviewers" / "euler"

    def test_data_files_copy_and_python_stays_out(self):
        stage_persona.stage(self.source, "euler", self.target)
        files = sorted(path.relative_to(self.staged()).as_posix() for path in self.staged().rglob("*") if path.is_file())
        self.assertEqual(files, ["QUALITY.md", "eval/cases/quality/one/diff.patch", "reviewer.json"])

    def test_python_case_inputs_stay_as_data(self):
        case = self.persona / "eval" / "cases" / "quality" / "one" / "app.py"
        case.write_text("value = 1\n", encoding="utf-8")
        stage_persona.stage(self.source, "euler", self.target)
        self.assertEqual((self.staged() / "eval" / "cases" / "quality" / "one" / "app.py").read_text(), "value = 1\n")
        self.assertFalse((self.staged() / "eval" / "extra_checks.py").exists())

    def test_symlink_fails(self):
        outside = Path(self.temp.name) / "secret.txt"
        outside.write_text("token\n", encoding="utf-8")
        os.symlink(outside, self.persona / "eval" / "cases" / "quality" / "one" / "leak.md")
        with self.assertRaisesRegex(stage_persona.StageError, "symlink"):
            stage_persona.stage(self.source, "euler", self.target)

    def test_symlinked_persona_directory_fails(self):
        real = Path(self.temp.name) / "elsewhere"
        real.mkdir()
        os.symlink(real, self.source / "reviewers" / "linked")
        with self.assertRaisesRegex(stage_persona.StageError, "symlink"):
            stage_persona.stage(self.source, "linked", self.target)

    def test_oversized_file_fails(self):
        big = self.persona / "big.md"
        big.write_bytes(b"x" * (stage_persona.MAX_FILE_BYTES + 1))
        with self.assertRaisesRegex(stage_persona.StageError, "exceeds"):
            stage_persona.stage(self.source, "euler", self.target)

    def test_unsafe_names_fail(self):
        for name in ("../euler", "_template", "Euler", "", "a" * 40):
            with self.subTest(name=name):
                with self.assertRaises(stage_persona.StageError):
                    stage_persona.stage(self.source, name, self.target)

    def test_existing_target_persona_fails(self):
        self.staged().mkdir(parents=True)
        with self.assertRaisesRegex(stage_persona.StageError, "exists"):
            stage_persona.stage(self.source, "euler", self.target)

    def test_missing_persona_fails(self):
        with self.assertRaisesRegex(stage_persona.StageError, "no persona"):
            stage_persona.stage(self.source, "havel", self.target)


if __name__ == "__main__":
    unittest.main()

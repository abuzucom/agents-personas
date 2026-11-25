"""Test engine/path_filter.py, the per-persona changed-file filter."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


path_filter = _load("path_filter")


class PatternParsingTest(unittest.TestCase):
    """Patterns come one per line. Blank lines and comments drop out."""

    def test_lines_comments_and_blanks(self):
        text = "src/payments/**\n\n# billing\n  docs/*.md  \n"
        self.assertEqual(path_filter.parse_patterns(text), ["src/payments/**", "docs/*.md"])

    def test_absolute_pattern_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "relative"):
            path_filter.parse_patterns("/etc/**")

    def test_parent_segment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "relative"):
            path_filter.parse_patterns("../x/**")

    def test_non_ascii_pattern_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ASCII"):
            path_filter.parse_patterns("café/**")

    def test_too_many_patterns_are_rejected(self):
        text = "\n".join(f"dir{index}/**" for index in range(path_filter.MAX_PATTERNS + 1))
        with self.assertRaisesRegex(ValueError, "at most"):
            path_filter.parse_patterns(text)


class MatchTest(unittest.TestCase):
    """A run happens when any changed file matches any pattern."""

    def test_empty_patterns_always_match(self):
        self.assertTrue(path_filter.any_match(["README.md"], []))

    def test_recursive_pattern_matches_nested_file(self):
        self.assertTrue(path_filter.any_match(["src/payments/core/charge.py"], ["src/payments/**"]))

    def test_single_star_stays_one_directory(self):
        self.assertFalse(path_filter.any_match(["docs/api/a.md"], ["docs/*.md"]))
        self.assertTrue(path_filter.any_match(["docs/a.md"], ["docs/*.md"]))

    def test_no_matching_file(self):
        self.assertFalse(path_filter.any_match(["README.md", "src/app.py"], ["src/payments/**"]))

    def test_no_files_never_match(self):
        self.assertFalse(path_filter.any_match([], ["src/**"]))


class CliTest(unittest.TestCase):
    """The CLI reads changed files and writes match=true or match=false."""

    def run_cli(self, files: list, patterns: str):
        with tempfile.TemporaryDirectory() as directory:
            files_path = Path(directory) / "files.json"
            output_path = Path(directory) / "output.txt"
            files_path.write_text(json.dumps(files), encoding="utf-8")
            environment = {**os.environ, "PATH_PATTERNS": patterns, "GITHUB_OUTPUT": str(output_path)}
            completed = subprocess.run(
                [sys.executable, str(ENGINE_DIR / "path_filter.py"), str(files_path)],
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )
            written = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
        return completed, written

    def test_match_writes_true(self):
        completed, written = self.run_cli(["src/payments/a.py"], "src/payments/**")
        self.assertEqual((completed.returncode, written), (0, "paths_match=true\n"))

    def test_no_match_writes_false(self):
        completed, written = self.run_cli(["README.md"], "src/payments/**")
        self.assertEqual((completed.returncode, written), (0, "paths_match=false\n"))

    def test_bad_pattern_fails(self):
        completed, written = self.run_cli(["README.md"], "/abs/**")
        self.assertEqual((completed.returncode, written), (1, ""))
        self.assertIn("relative", completed.stderr)


if __name__ == "__main__":
    unittest.main()

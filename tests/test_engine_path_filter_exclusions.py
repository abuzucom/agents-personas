"""Test the exclusion patterns in engine/path_filter.py.

A pattern that starts with "!" excludes the files it matches. A pull request
needs a review when at least one changed file matches an include pattern,
or any file when no include exists, and matches no exclusion. A pull request
that touches only excluded files skips the review.
"""

import importlib.util
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
REPO_ROOT = ENGINE_DIR.parent


def _load():
    spec = importlib.util.spec_from_file_location("path_filter", ENGINE_DIR / "path_filter.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


path_filter = _load()
SKIP_ONLY = path_filter.parse_patterns("!CHANGELOG.md\n!README.md")


class ExclusionTest(unittest.TestCase):
    """Exclusions remove files from the match set."""

    def test_excluded_files_skip_review(self):
        for files in (["CHANGELOG.md"], ["README.md"], ["CHANGELOG.md", "README.md"]):
            with self.subTest(files=files):
                self.assertFalse(path_filter.any_match(files, SKIP_ONLY))

    def test_any_other_file_runs_review(self):
        for files in (["CHANGELOG.md", "engine/run_review.py"], ["reviewers/euler/README.md"], ["docs/README.md"]):
            with self.subTest(files=files):
                self.assertTrue(path_filter.any_match(files, SKIP_ONLY))

    def test_exclusion_applies_after_includes(self):
        patterns = path_filter.parse_patterns("engine/**\n!engine/apparmor/**")
        self.assertTrue(path_filter.any_match(["engine/run_review.py"], patterns))
        self.assertFalse(path_filter.any_match(["engine/apparmor/bwrap"], patterns))
        self.assertFalse(path_filter.any_match(["docs/plan.md"], patterns))

    def test_empty_patterns_select_all(self):
        self.assertTrue(path_filter.any_match(["CHANGELOG.md"], []))

    def test_bare_or_unsafe_exclusions_refused(self):
        for text in ("!", "!/etc/passwd", "!../x", "! "):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    path_filter.parse_patterns(text)


class SelfReviewCallerTest(unittest.TestCase):
    """Both self-review callers skip pull requests that touch only CHANGELOG.md or README.md."""

    def test_callers_pass_the_two_exclusions(self):
        import yaml

        for name in ("foucault-security-review-pr.yml", "euler-quality-review-pr.yml"):
            with self.subTest(caller=name):
                workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
                job = next(iter(workflow["jobs"].values()))
                patterns = path_filter.parse_patterns(job["with"]["paths"])
                self.assertEqual(patterns, ["!CHANGELOG.md", "!README.md"])


if __name__ == "__main__":
    unittest.main()

"""Test that build_pr_case diffs from the merge base.

The workflow passes the current tip of the base branch as base. When the
base branch moves after the pull request branches off, a two-dot diff of
base..head shows the newer base commits in reverse, as if the pull request
undid them. GitHub's pull request diff starts at the merge base. The case
must match it.
"""
import unittest

from tests import test_engine_build_pr_case as fixture

_git = fixture._git


class MovedBaseTest(fixture.RepositoryFixture):
    """A base branch that moves after branching adds nothing to the case."""

    def setUp(self):
        super().setUp()
        _git(self.repo, "switch", "-q", "-c", "feature", self.head)
        (self.repo / "feature.py").write_text("feature = 1\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "feature")
        self.feature = _git(self.repo, "rev-parse", "HEAD")
        _git(self.repo, "switch", "-q", "main")
        _git(self.repo, "reset", "-q", "--hard", self.head)
        (self.repo / "CHANGELOG.md").write_text("## 2.0.0\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "release on main")
        self.moved_base = _git(self.repo, "rev-parse", "HEAD")

    def test_changed_files_come_from_the_pull_request_only(self):
        manifest = self.build(base=self.moved_base, head=self.feature)
        self.assertEqual(manifest["changed_files"], ["feature.py"])

    def test_newer_base_commits_never_reach_the_patches(self):
        manifest = self.build(base=self.moved_base, head=self.feature)
        files = self.envelopes(manifest)[0]["REVIEW_TARGET"]["files"]
        self.assertEqual(sorted(files), ["feature.py"])
        self.assertNotIn("CHANGELOG.md", str(self.envelopes(manifest)))

    def test_recorded_base_stays_the_branch_tip(self):
        self.assertEqual(self.build(base=self.moved_base, head=self.feature)["base_sha"], self.moved_base)


if __name__ == "__main__":
    unittest.main()

"""Exercise branch preflight independently of the runner checkout state.

The class below copies CiBranchFixtureTest from the template module
tests/test_ci_branch_fixtures.py unchanged. That template module also
reads the declined immutable-conflict-check.yml workflow. The adoption
keeps the portable class here so hook coverage reaches the valid-branch
paths of hooks/enforce_branch_name.py.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_enforce_branch_name import BLOCKING_EXIT_CODE, REPO_ROOT, hook


class CiBranchFixtureTest(unittest.TestCase):
    """Use real compliant metadata for every valid-branch handler path."""

    def test_valid_branch_dispatch_uses_isolated_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / ".git").mkdir()
            (root / ".git" / "HEAD").write_text("ref: refs/heads/fix/fixture\n", encoding="utf-8")
            (root / "scripts").mkdir()
            for name in ("check_branch_name.py", "trusted_git.py", "branch_name_bans.txt"):
                (root / "scripts" / name).write_bytes((REPO_ROOT / "scripts" / name).read_bytes())
            cases = (
                ({"tool_name": [], "tool_input": {}}, BLOCKING_EXIT_CODE),
                ({"tool_name": "Write", "tool_input": {"file_path": "notes.txt", "content": "text"}}, 0),
                ({"tool_name": "Bash", "tool_input": {"command": "echo safe"}}, 0),
                ({"tool_name": "Bash", "tool_input": {"command": "python scripts/read_git_state.py branch"}}, 0),
            )
            with patch.object(hook.core, "policy_root", return_value=str(root)):
                for payload, expected in cases:
                    with self.subTest(payload=payload):
                        self.assertEqual(hook._handle_pre_tool_use(payload, str(root), "claude"), expected)


if __name__ == "__main__":
    unittest.main()

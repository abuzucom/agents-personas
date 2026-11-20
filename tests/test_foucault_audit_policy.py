"""Test reviewers/foucault/scripts/check_audit_policy.py, ported from foucault 9ec9681."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "reviewers" / "foucault" / "scripts" / "check_audit_policy.py"
_SPEC = importlib.util.spec_from_file_location("check_audit_policy", SCRIPT)
check_audit_policy = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_audit_policy)
find_violations = check_audit_policy.find_violations


def _violations(content: bytes) -> list:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "AUDIT.md"
        path.write_bytes(content)
        return find_violations(path)


class AuditPolicyTest(unittest.TestCase):
    """AUDIT.md keeps its required controls, size, ASCII, LF, and width."""

    def test_current_policy_passes(self):
        self.assertEqual(find_violations(check_audit_policy.DEFAULT_POLICY), [])

    def test_missing_required_control_fails(self):
        self.assertTrue(any("missing required" in item for item in _violations(b"## 0. Review Modes\n")))

    def test_long_prose_line_fails(self):
        self.assertTrue(any("exceeds" in item for item in _violations(b"x" * 121)))

    def test_long_table_row_is_allowed(self):
        self.assertFalse(any("exceeds" in item for item in _violations(b"| " + b"x" * 130)))

    def test_non_ascii_policy_fails(self):
        self.assertTrue(any("ASCII" in item for item in _violations("cafeé".encode("utf-8"))))

    def test_crlf_policy_fails(self):
        self.assertTrue(any("LF" in item for item in _violations(b"## 0. Review Modes\r\n")))

    def test_oversized_policy_fails(self):
        findings = _violations(b"x" * (32 * 1024 + 1))
        self.assertTrue(any("smaller than" in item for item in findings))

    def test_duplicate_heading_fails(self):
        self.assertTrue(any("duplicate" in item for item in _violations(b"## Duplicate\n## Duplicate\n")))

    def test_git_checks_out_the_prompt_with_lf_on_every_platform(self):
        # Windows checks out text with CRLF unless .gitattributes pins LF. The
        # checker rejects CRLF, so the attribute keeps the prompt valid there.
        completed = subprocess.run(["git", "check-attr", "eol", "--", "reviewers/foucault/AUDIT.md"],
                                   cwd=SCRIPT.parents[3], capture_output=True, text=True, check=True)
        self.assertEqual(completed.stdout.strip(), "reviewers/foucault/AUDIT.md: eol: lf")

    def test_script_checks_the_persona_prompt_by_default(self):
        completed = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("AUDIT.md", completed.stdout)


if __name__ == "__main__":
    unittest.main()

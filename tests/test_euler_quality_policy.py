"""Tests for reviewers/euler/scripts/check_quality_policy.py."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Ported from abuzucom/euler at 9488a8c. REPO_ROOT names the euler persona directory.
REPO_ROOT = Path(__file__).resolve().parent.parent / "reviewers" / "euler"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_quality_policy as policy  # resolved through the path set above

VALID_HEADER = """# QUALITY.md

## 0. Review Modes

Final lines use `VERDICT: APPROVE | BLOCK | NEEDS-HUMAN`, `RISK:`, and `RISK (partial):`.

```
VERDICT_JSON: {"schema_version": "1"}
```
"""


def build_policy_text(class_ids: list[str], tier: str = "Graded") -> str:
    """Return a minimal policy text holding the given class headings."""
    headings = [f"### {class_id} Sample class {class_id} ({tier})" for class_id in class_ids]
    return VALID_HEADER + "\n" + "\n\n- Flag the condition.\n\n".join(headings) + "\n- Flag the condition.\n"


class PolicyFixtureCase(unittest.TestCase):
    """Base case writing fixture policies to a temporary directory."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def write_policy(self, text: str | bytes) -> Path:
        """Write the fixture and return its path."""
        path = Path(self.temp_dir.name) / "QUALITY.md"
        if isinstance(text, str):
            path.write_text(text, encoding="utf-8", newline="\n")
        else:
            path.write_bytes(text)
        return path

    def valid_text(self) -> str:
        """Return a fixture that satisfies every rule."""
        return build_policy_text(sorted(policy.REQUIRED_CLASS_IDS))


class RealPolicyTest(unittest.TestCase):
    """The committed policy files pass the checker."""

    def test_quality_md_passes(self) -> None:
        self.assertEqual(policy.find_violations(REPO_ROOT / "QUALITY.md"), [])

    def test_agents_md_passes_prose_checks(self) -> None:
        self.assertEqual(policy.find_violations(REPO_ROOT.parent.parent / "AGENTS.md", prose_only=True), [])


class ClassRuleTest(PolicyFixtureCase):
    """Class headings and tiers."""

    def test_valid_fixture_passes(self) -> None:
        self.assertEqual(policy.find_violations(self.write_policy(self.valid_text())), [])

    def test_missing_class_fails(self) -> None:
        class_ids = sorted(policy.REQUIRED_CLASS_IDS - {"Q4"})
        violations = policy.find_violations(self.write_policy(build_policy_text(class_ids)))
        self.assertIn("missing class: Q4", violations)

    def test_invalid_tier_fails(self) -> None:
        text = self.valid_text().replace("### Q1 Sample class Q1 (Graded)", "### Q1 Sample class Q1 (Severe)")
        violations = policy.find_violations(self.write_policy(text))
        self.assertIn("class heading without a valid tier: ### Q1 Sample class Q1 (Severe)", violations)

    def test_duplicate_class_fails(self) -> None:
        text = self.valid_text() + "\n### Q1 Another Q1 (Advisory)\n"
        violations = policy.find_violations(self.write_policy(text))
        self.assertIn("duplicate class: Q1", violations)

    def test_parse_classes_reads_tier_script(self) -> None:
        text = "### Q3 Regex backtracking (Graded +script)\n### Q1 Logic (Blocking)\n"
        classes = policy.parse_classes(text)
        self.assertEqual(classes["Q3"], policy.PolicyClass("Q3", "Regex backtracking", "Graded", True))
        self.assertEqual(classes["Q1"], policy.PolicyClass("Q1", "Logic", "Blocking", False))


class StructureRuleTest(PolicyFixtureCase):
    """Verdict tokens, headings, encoding, width, and size."""

    def test_missing_verdict_token_fails(self) -> None:
        text = self.valid_text().replace("RISK (partial):", "RISK partial")
        violations = policy.find_violations(self.write_policy(text))
        self.assertIn("missing required text: RISK (partial):", violations)

    def test_duplicate_heading_fails(self) -> None:
        text = self.valid_text() + "\n## 0. Review Modes\n"
        violations = policy.find_violations(self.write_policy(text))
        self.assertIn("duplicate heading: ## 0. Review Modes", violations)

    def test_non_ascii_fails(self) -> None:
        text = self.valid_text() + "\nCafé prose.\n"
        violations = policy.find_violations(self.write_policy(text))
        self.assertIn("policy must contain ASCII text only", violations)

    def test_crlf_fails(self) -> None:
        text = self.valid_text().replace("\n", "\r\n").encode("ascii")
        violations = policy.find_violations(self.write_policy(text))
        self.assertIn("policy must use LF line endings", violations)

    def test_long_prose_line_fails(self) -> None:
        text = self.valid_text() + "\n" + "word " * 30 + "\n"
        violations = policy.find_violations(self.write_policy(text))
        self.assertTrue(any("exceeds 120 characters" in item for item in violations))

    def test_long_table_line_passes(self) -> None:
        text = self.valid_text() + "\n| " + "cell " * 30 + "|\n"
        self.assertEqual(policy.find_violations(self.write_policy(text)), [])

    def test_oversized_policy_fails(self) -> None:
        text = self.valid_text() + ("- Flag the condition.\n" * 2000)
        violations = policy.find_violations(self.write_policy(text))
        self.assertIn("policy exceeds 32768 bytes", violations)

    def test_missing_file_fails(self) -> None:
        missing = Path(self.temp_dir.name) / "absent.md"
        self.assertEqual(policy.find_violations(missing), [f"missing policy: {missing}"])


class DashRuleTest(PolicyFixtureCase):
    """Prose dash rules."""

    def test_double_hyphen_prose_fails(self) -> None:
        text = self.valid_text() + "\nThe build failed -- the cache was stale.\n"
        violations = policy.find_violations(self.write_policy(text))
        self.assertTrue(any("prose dash" in item for item in violations))

    def test_spaced_hyphen_prose_fails(self) -> None:
        text = self.valid_text() + "\nThe build failed - the cache was stale.\n"
        violations = policy.find_violations(self.write_policy(text))
        self.assertTrue(any("prose dash" in item for item in violations))

    def test_code_span_bullet_comment_pass(self) -> None:
        extra = "\n- A bullet with `a -- b` inside a code span.\n<!-- an HTML comment -->\n| a | - |\n"
        self.assertEqual(policy.find_violations(self.write_policy(self.valid_text() + extra)), [])

    def test_prose_only_skips_class_rules(self) -> None:
        path = self.write_policy("# AGENTS.md\n\nPlain prose.\n")
        self.assertEqual(policy.find_violations(path, prose_only=True), [])

    def test_dash_inside_tilde_fence_passes(self) -> None:
        text = "# Doc\n\n~~~\nrun --flag - value\n~~~\n"
        self.assertEqual(policy.find_line_violations(text), [])

    def test_short_backticks_stay_fenced(self) -> None:
        text = "# Doc\n\n````\n```\nrun --flag - value\n```\n````\n"
        self.assertEqual(policy.find_line_violations(text), [])

    def test_prose_after_tilde_fence_checked(self) -> None:
        text = "# Doc\n\n~~~\ncode\n~~~\nThe build failed - the cache was stale.\n"
        self.assertEqual(policy.find_line_violations(text), ["line 6 uses a prose dash"])

    def test_tilde_keeps_backtick_fence(self) -> None:
        text = "# Doc\n\n```\n~~~\nrun --flag - value\n```\n"
        self.assertEqual(policy.find_line_violations(text), [])


class LineEndingAttributeTest(unittest.TestCase):
    """Windows checks out text with CRLF unless .gitattributes pins LF. The checker rejects CRLF."""

    def test_prompt_checks_out_lf(self) -> None:
        completed = subprocess.run(
            ["git", "check-attr", "eol", "--", "reviewers/euler/QUALITY.md"],
            cwd=REPO_ROOT.parent.parent,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(completed.stdout.strip(), "reviewers/euler/QUALITY.md: eol: lf")


if __name__ == "__main__":
    unittest.main()

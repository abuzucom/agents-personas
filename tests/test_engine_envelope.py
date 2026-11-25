"""Test the fenced review envelope in engine/envelope.py."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


envelope = _load("envelope")


def _build(title="Fix parser", body="Body text.", files=None, metadata=None) -> dict:
    text = envelope.build_envelope(
        "generay",
        "time",
        files if files is not None else {"src/app.py": "+x = 1\n"},
        title,
        body,
        metadata or {"pr_number": 7},
    )
    return json.loads(text)


class EnvelopeLayoutTest(unittest.TestCase):
    """Untrusted pull request content stays inside REVIEW_TARGET."""

    def test_trusted_context_names_persona_mode(self):
        trusted = _build()["TRUSTED_CONTEXT"]
        self.assertEqual((trusted["persona"], trusted["mode"]), ("generay", "time"))
        self.assertEqual(trusted["metadata"], {"pr_number": 7})

    def test_pr_fields_stay_in_target(self):
        document = _build(title="T1", body="B1", files={"a.py": "+P1\n"})
        target = document["REVIEW_TARGET"]
        self.assertEqual((target["title"], target["body"], target["files"]), ("T1", "B1", {"a.py": "+P1\n"}))
        trusted_text = json.dumps(document["TRUSTED_CONTEXT"])
        for marker in ("T1", "B1", "a.py", "P1"):
            self.assertNotIn(marker, trusted_text)

    def test_target_note_marks_data(self):
        self.assertIn("data", _build()["REVIEW_TARGET"]["note"])

    def test_sections_carry_sha256_digests(self):
        document = _build()
        for section in ("TRUSTED_CONTEXT", "REVIEW_TARGET"):
            self.assertEqual(len(document[section]["sha256"]), 64)

    def test_pr_text_metadata_rejected(self):
        with self.assertRaises(ValueError):
            _build(metadata={"title": "x"})


class FieldCapTest(unittest.TestCase):
    """The engine caps the title and body and records each truncation."""

    def test_short_fields_are_unchanged(self):
        document = _build()
        self.assertEqual(document["TRUSTED_CONTEXT"]["truncated"], [])

    def test_long_title_truncated_recorded(self):
        document = _build(title="t" * (envelope.MAX_TITLE_CHARS + 50))
        title = document["REVIEW_TARGET"]["title"]
        self.assertTrue(title.endswith(envelope.TRUNCATION_MARKER))
        self.assertLessEqual(len(title), envelope.MAX_TITLE_CHARS + len(envelope.TRUNCATION_MARKER))
        self.assertEqual(document["TRUSTED_CONTEXT"]["truncated"], ["title"])

    def test_long_body_truncated_recorded(self):
        document = _build(body="b" * (envelope.MAX_BODY_CHARS + 1))
        self.assertEqual(document["TRUSTED_CONTEXT"]["truncated"], ["body"])


class FenceRuleTest(unittest.TestCase):
    """The system prompt gains one fixed rule about untrusted content."""

    def test_rule_is_appended_once(self):
        prompt = envelope.with_fence_rule("Persona prompt.")
        self.assertTrue(prompt.startswith("Persona prompt."))
        self.assertIn(envelope.FENCE_RULE, prompt)
        self.assertEqual(envelope.with_fence_rule(prompt).count(envelope.FENCE_RULE), 1)

    def test_rule_names_the_untrusted_section(self):
        self.assertIn("REVIEW_TARGET", envelope.FENCE_RULE)


if __name__ == "__main__":
    unittest.main()

"""Test the per-model format note and the closing reminder in engine/call_model.py.

A provider profile can carry a format_note. The engine appends it to the
trusted system prompt for that profile only. Every request also ends the
user message with a short trusted reminder after the review envelope.
Models weight the last instruction they read most.
"""

import importlib.util
import json
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"


def _load():
    spec = importlib.util.spec_from_file_location("call_model", ENGINE_DIR / "call_model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


call_model = _load()
NOTE = "- Model note: start the second report line with Scope:."


def _profile(protocol: str, **extra) -> dict:
    return {
        "protocol": protocol,
        "endpoint": call_model.ENDPOINTS_BY_PROTOCOL[protocol],
        "model": "m",
        "name": protocol,
        **extra,
    }


def _texts(protocol: str, **extra) -> tuple[str, str]:
    """Return the system text and the user text of one request."""
    body = json.loads(call_model._build_request(_profile(protocol, **extra), "SYSTEM", "CASE", "k").data)
    if protocol in ("ollama", "openai-compatible"):
        return body["messages"][0]["content"], body["messages"][1]["content"]
    if protocol == "anthropic":
        return body["system"], body["messages"][0]["content"]
    return body["systemInstruction"]["parts"][0]["text"], body["contents"][0]["parts"][0]["text"]


class FormatNoteTest(unittest.TestCase):
    """A profile note reaches the system prompt of that profile only."""

    def test_note_follows_the_system_prompt(self):
        for protocol in call_model.ALLOWED_PROTOCOLS:
            with self.subTest(protocol=protocol):
                system, _user = _texts(protocol, format_note=NOTE)
                self.assertEqual(system, "SYSTEM\n" + NOTE)

    def test_noteless_profile_keeps_prompt(self):
        for protocol in call_model.ALLOWED_PROTOCOLS:
            with self.subTest(protocol=protocol):
                self.assertEqual(_texts(protocol)[0], "SYSTEM")

    def test_invalid_notes_are_refused(self):
        for note in (7, "", "x" * (call_model.MAX_FORMAT_NOTE_CHARS + 1), "bell\x07", "café"):
            with self.subTest(note=note):
                with self.assertRaises(call_model.ProviderError):
                    call_model.format_note({"format_note": note})

    def test_shipped_active_profile_carries_note(self):
        config = json.loads((ENGINE_DIR / "model_providers.json").read_text(encoding="utf-8"))
        profile = call_model._load_profile(config["active_provider"])
        self.assertIn("Scope:", call_model.format_note(profile))


class ClosingReminderTest(unittest.TestCase):
    """Every request ends the user message with the trusted reminder."""

    def test_reminder_follows_the_case_text(self):
        for protocol in call_model.ALLOWED_PROTOCOLS:
            with self.subTest(protocol=protocol):
                self.assertEqual(_texts(protocol)[1], "CASE" + call_model.REPORT_REMINDER)

    def test_reminder_names_opening_closing_lines(self):
        reminder = call_model.REPORT_REMINDER
        for marker in ("**Mode:**", "Scope:", "Unseen:", "VERDICT", "VERDICT_JSON", "REVIEW_TARGET"):
            with self.subTest(marker=marker):
                self.assertIn(marker, reminder)


if __name__ == "__main__":
    unittest.main()

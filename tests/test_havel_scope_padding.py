"""Test that a padded havel regimes value gets the note of its trimmed scope.

The engine resolves the caller value and strips it before the note lookup.
The havel hook strips each name before the scope check. A value with spaces
around it therefore passes the hook and carries the same note as the trimmed
value.
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PERSONA_DIR = REPO_ROOT / "reviewers" / "havel"
UNCHECKED_PHRASE = "Regime-specific issues may exist that this run did not check."


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reviewers = _load("reviewers", REPO_ROOT / "engine" / "reviewers.py")
hooks = _load("havel_padding_hooks", PERSONA_DIR / "review_hooks.py")
MANIFEST = json.loads((PERSONA_DIR / "reviewer.json").read_text(encoding="utf-8"))


def _notes(regimes: str) -> list[str]:
    resolved = reviewers.resolve_options(MANIFEST, json.dumps({"regimes": regimes}))
    return reviewers.option_notes(MANIFEST, reviewers.trusted_option_values(MANIFEST, resolved))


class PaddedScopeTest(unittest.TestCase):
    """Spaces around a scope change neither the check nor the note."""

    def test_padded_values_carry_note(self):
        for padded, trimmed in (("  ", ""), (" baseline ", "baseline"), ("undeclared ", "undeclared")):
            with self.subTest(regimes=padded):
                notes = _notes(padded)
                self.assertEqual(notes, _notes(trimmed))
                self.assertEqual(len(notes), 1)
                self.assertIn(UNCHECKED_PHRASE, notes[0])

    def test_padded_list_lacks_note(self):
        self.assertEqual(_notes("  eu ,  us  "), [])

    def test_padded_values_pass_the_hook(self):
        for regimes in ("  ", " baseline ", "undeclared ", "  eu ,  us  "):
            with self.subTest(regimes=regimes):
                context = hooks.case_context("/nonexistent", [], {}, {"regimes": regimes})
                self.assertEqual(context, {"context": {}, "unreviewed": []})


if __name__ == "__main__":
    unittest.main()

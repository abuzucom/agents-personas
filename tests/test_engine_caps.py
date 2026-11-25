"""Test per-mode caps in reviewer.json and their resolution in engine/reviewers.py."""

import importlib.util
import json
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


reviewers = _load("reviewers")


def _findings(mode_extra: dict) -> list:
    mode = {"prompt": "P.md", "review": True, "default": True}
    mode.update(mode_extra)
    with tempfile.TemporaryDirectory() as directory:
        persona_dir = Path(directory) / "reviewers" / "euler"
        persona_dir.mkdir(parents=True)
        (persona_dir / "P.md").write_text("prompt\n", encoding="ascii")
        manifest = {"persona": "euler", "function": "quality", "modes": {"quality": mode}}
        (persona_dir / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
        return reviewers.validate_persona(persona_dir)


class CapSchemaTest(unittest.TestCase):
    """Caps are optional positive integers at or below the engine ceiling."""

    def test_valid_caps_pass(self):
        self.assertEqual(_findings({"max_chunks": 5, "max_envelope_bytes": 100_000}), [])

    def test_zero_cap_is_reported(self):
        self.assertTrue(any("max_chunks" in item for item in _findings({"max_chunks": 0})))

    def test_boolean_cap_is_reported(self):
        self.assertTrue(any("max_chunks" in item for item in _findings({"max_chunks": True})))

    def test_cap_above_engine_ceiling_reported(self):
        findings = _findings({"max_envelope_bytes": reviewers.CAP_CEILINGS["max_envelope_bytes"] + 1})
        self.assertTrue(any("max_envelope_bytes" in item for item in findings))


class CapResolutionTest(unittest.TestCase):
    """A caller request can lower a cap and never raise it."""

    MODE = {"prompt": "P.md", "review": True, "default": True, "max_chunks": 8}

    def test_defaults_apply_without_mode_caps(self):
        caps = reviewers.resolve_caps({"prompt": "P.md", "review": True})
        self.assertEqual(caps["max_chunks"], reviewers.CAP_DEFAULTS["max_chunks"])
        self.assertEqual(caps["max_envelope_bytes"], reviewers.CAP_DEFAULTS["max_envelope_bytes"])
        self.assertEqual(caps["clamped"], [])

    def test_lower_request_applies(self):
        caps = reviewers.resolve_caps(self.MODE, {"max_chunks": 3})
        self.assertEqual((caps["max_chunks"], caps["clamped"]), (3, []))

    def test_higher_request_clamped_recorded(self):
        caps = reviewers.resolve_caps(self.MODE, {"max_chunks": 50})
        self.assertEqual((caps["max_chunks"], caps["clamped"]), (8, ["max_chunks"]))

    def test_invalid_request_is_rejected(self):
        with self.assertRaises(reviewers.ReviewerError):
            reviewers.resolve_caps(self.MODE, {"max_chunks": 0})

    def test_unknown_request_key_is_rejected(self):
        with self.assertRaises(reviewers.ReviewerError):
            reviewers.resolve_caps(self.MODE, {"max_tokens": 5})


if __name__ == "__main__":
    unittest.main()

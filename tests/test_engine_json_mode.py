"""Test the optional json_mode key of a reviewer.json mode."""
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


def _findings(json_mode: object) -> list:
    with tempfile.TemporaryDirectory() as directory:
        persona_dir = Path(directory) / "reviewers" / "foucault"
        persona_dir.mkdir(parents=True)
        (persona_dir / "AUDIT.md").write_text("prompt\n", encoding="ascii")
        mode = {"prompt": "AUDIT.md", "review": True, "default": True, "json_mode": json_mode}
        manifest = {"persona": "foucault", "function": "security", "modes": {"security": mode}}
        (persona_dir / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
        return reviewers.validate_persona(persona_dir)


class JsonModeSchemaTest(unittest.TestCase):
    """json_mode is a short printable ASCII string."""

    def test_valid_value_passes(self):
        self.assertEqual(_findings("PR"), [])

    def test_empty_value_is_reported(self):
        self.assertTrue(any("json_mode" in item for item in _findings("")))

    def test_non_string_value_is_reported(self):
        self.assertTrue(any("json_mode" in item for item in _findings(7)))

    def test_control_character_is_reported(self):
        self.assertTrue(any("json_mode" in item for item in _findings("P\nR")))

    def test_overlong_value_is_reported(self):
        value = "x" * (reviewers.MAX_NAME_LENGTH + 1)
        self.assertTrue(any("json_mode" in item for item in _findings(value)))


if __name__ == "__main__":
    unittest.main()

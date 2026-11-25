"""Test persona options: manifest declarations and caller values."""

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

OPTIONS = {
    "exclude_paths": {"type": "string", "default": ""},
    "strict": {"type": "boolean", "default": False},
    "depth": {"type": "integer", "default": 3},
}
MANIFEST = {
    "persona": "euler",
    "function": "quality",
    "options": OPTIONS,
    "modes": {"quality": {"prompt": "QUALITY.md", "review": True, "default": True}},
}


def _findings(options: object) -> list:
    with tempfile.TemporaryDirectory() as directory:
        persona_dir = Path(directory) / "reviewers" / "euler"
        persona_dir.mkdir(parents=True)
        (persona_dir / "QUALITY.md").write_text("prompt\n", encoding="ascii")
        manifest = {**MANIFEST, "options": options}
        (persona_dir / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
        return reviewers.validate_persona(persona_dir)


class OptionSchemaTest(unittest.TestCase):
    """options declares each caller option with a type and a default."""

    def test_declared_options_pass(self):
        self.assertEqual(_findings(OPTIONS), [])

    def test_options_must_be_an_object(self):
        self.assertTrue(any("'options' must be a JSON object" in item for item in _findings([])))

    def test_option_name_must_snake_case(self):
        findings = _findings({"Exclude-Paths": {"type": "string", "default": ""}})
        self.assertTrue(any("invalid option name" in item for item in findings), findings)

    def test_option_type_must_be_known(self):
        findings = _findings({"exclude_paths": {"type": "list", "default": []}})
        self.assertTrue(any("type must be one of" in item for item in findings), findings)

    def test_default_must_match_the_type(self):
        findings = _findings({"depth": {"type": "integer", "default": "3"}})
        self.assertTrue(any("default does not match type 'integer'" in item for item in findings), findings)

    def test_unknown_option_key_is_reported(self):
        findings = _findings({"depth": {"type": "integer", "default": 3, "max": 9}})
        self.assertTrue(any("unknown key 'max'" in item for item in findings), findings)


class ResolveOptionsTest(unittest.TestCase):
    """A caller value replaces a default. The engine rejects anything undeclared."""

    def test_empty_request_returns_the_defaults(self):
        self.assertEqual(reviewers.resolve_options(MANIFEST, ""), {"exclude_paths": "", "strict": False, "depth": 3})

    def test_request_overrides_a_default(self):
        resolved = reviewers.resolve_options(MANIFEST, '{"exclude_paths": "tests/**", "depth": 5}')
        self.assertEqual(resolved, {"exclude_paths": "tests/**", "strict": False, "depth": 5})

    def test_undeclared_option_is_rejected(self):
        with self.assertRaisesRegex(reviewers.ReviewerError, "undeclared option 'regimes'"):
            reviewers.resolve_options(MANIFEST, '{"regimes": "gdpr"}')

    def test_wrong_type_is_rejected(self):
        with self.assertRaisesRegex(reviewers.ReviewerError, "option 'strict' must be a boolean"):
            reviewers.resolve_options(MANIFEST, '{"strict": "yes"}')
        with self.assertRaisesRegex(reviewers.ReviewerError, "option 'depth' must be an integer"):
            reviewers.resolve_options(MANIFEST, '{"depth": true}')

    def test_request_must_json_object(self):
        for text in ("[1]", "{", "3"):
            with self.subTest(text=text), self.assertRaisesRegex(reviewers.ReviewerError, "JSON object"):
                reviewers.resolve_options(MANIFEST, text)

    def test_string_value_bounded_ascii(self):
        with self.assertRaisesRegex(reviewers.ReviewerError, "printable ASCII"):
            reviewers.resolve_options(MANIFEST, json.dumps({"exclude_paths": "aé"}))
        long_value = "x" * (reviewers.MAX_OPTION_CHARS + 1)
        with self.assertRaisesRegex(reviewers.ReviewerError, "at most"):
            reviewers.resolve_options(MANIFEST, json.dumps({"exclude_paths": long_value}))

    def test_string_value_keeps_newlines_tabs(self):
        resolved = reviewers.resolve_options(MANIFEST, json.dumps({"exclude_paths": "tests/**\n\tdocs/**"}))
        self.assertEqual(resolved["exclude_paths"], "tests/**\n\tdocs/**")
        with self.assertRaisesRegex(reviewers.ReviewerError, "printable ASCII"):
            reviewers.resolve_options(MANIFEST, json.dumps({"exclude_paths": "a\rb"}))

    def test_optionless_persona_accepts_empty(self):
        manifest = {key: value for key, value in MANIFEST.items() if key != "options"}
        self.assertEqual(reviewers.resolve_options(manifest, "{}"), {})
        with self.assertRaisesRegex(reviewers.ReviewerError, "undeclared option"):
            reviewers.resolve_options(manifest, '{"depth": 1}')


if __name__ == "__main__":
    unittest.main()

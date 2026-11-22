"""Test local modes: manifest keys for modes that run only on a workstation."""

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

REVIEW_MODE = {"prompt": "AUDIT.md", "review": True, "default": True, "json_mode": "PR"}
FILE_MODE = {
    "prompt": "AUDIT.md",
    "local": True,
    "json_mode": "File",
    "verdict_line": "RISK",
    "verdicts": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE-FOUND"],
}


def _findings(local_mode: dict) -> list:
    with tempfile.TemporaryDirectory() as directory:
        persona_dir = Path(directory) / "reviewers" / "foucault"
        persona_dir.mkdir(parents=True)
        (persona_dir / "AUDIT.md").write_text("prompt\n", encoding="ascii")
        manifest = {
            "persona": "foucault",
            "function": "security",
            "modes": {"security": REVIEW_MODE, "file": local_mode},
        }
        (persona_dir / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
        return reviewers.validate_persona(persona_dir)


class LocalModeSchemaTest(unittest.TestCase):
    """local is a third delivery. verdict_line and verdicts describe its verdict."""

    def test_local_mode_passes(self):
        self.assertEqual(_findings(FILE_MODE), [])

    def test_local_flag_must_be_boolean(self):
        findings = _findings({**FILE_MODE, "local": "yes"})
        self.assertTrue(any("'local' must be true or false" in item for item in findings), findings)

    def test_mode_without_any_delivery_is_reported(self):
        mode = {key: value for key, value in FILE_MODE.items() if key != "local"}
        self.assertTrue(any("no delivery" in item for item in _findings(mode)))

    def test_verdicts_must_be_a_string_list(self):
        findings = _findings({**FILE_MODE, "verdicts": "HIGH"})
        self.assertTrue(any("'verdicts' must be" in item for item in findings), findings)

    def test_verdict_line_must_be_printable_ascii(self):
        findings = _findings({**FILE_MODE, "verdict_line": "RISK\n"})
        self.assertTrue(any("'verdict_line' must be" in item for item in findings), findings)

    def test_verdict_keys_require_a_local_only_mode(self):
        mode = {**FILE_MODE, "review": True}
        findings = _findings(mode)
        self.assertTrue(any("local-only" in item for item in findings), findings)

    def test_local_mode_has_no_review_delivery(self):
        manifest = {"persona": "foucault", "modes": {"security": REVIEW_MODE, "file": FILE_MODE}}
        with self.assertRaisesRegex(reviewers.ReviewerError, "no review delivery"):
            reviewers.resolve_review_modes(manifest, "file")

    def test_verdict_rules_default_to_the_engine_verdicts(self):
        rules = reviewers.verdict_rules(REVIEW_MODE)
        self.assertEqual(rules, ("VERDICT", ("APPROVE", "BLOCK", "NEEDS-HUMAN")))

    def test_verdict_rules_read_a_local_mode(self):
        rules = reviewers.verdict_rules(FILE_MODE)
        self.assertEqual(rules, ("RISK", ("CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE-FOUND")))


if __name__ == "__main__":
    unittest.main()

"""Test per-mode finding rules: schema validation and response enforcement."""

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
validator = _load("check_review_response")

FOUCAULT_RULES = {
    "keys": ["severity", "class", "file", "line", "title"],
    "severities": ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
    "class_prefix": "2.",
}


def _finding(**changes) -> dict:
    finding = {"severity": "HIGH", "class": "2.5", "file": "app.py", "line": 3, "title": "Injection"}
    finding.update(changes)
    return finding


def _response(findings: list) -> str:
    payload = {"mode": "PR", "verdict": "BLOCK", "findings": findings}
    return f"Mode: PR\nScope.\nVERDICT: BLOCK\nVERDICT_JSON: {json.dumps(payload)}\n"


def _schema_findings(rules: object) -> list:
    with tempfile.TemporaryDirectory() as directory:
        persona_dir = Path(directory) / "reviewers" / "foucault"
        persona_dir.mkdir(parents=True)
        (persona_dir / "AUDIT.md").write_text("prompt\n", encoding="ascii")
        mode = {"prompt": "AUDIT.md", "review": True, "default": True, "finding_rules": rules}
        manifest = {"persona": "foucault", "function": "security", "modes": {"security": mode}}
        (persona_dir / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
        return reviewers.validate_persona(persona_dir)


class FindingRulesSchemaTest(unittest.TestCase):
    """finding_rules accepts keys, severities, and a class prefix."""

    def test_foucault_rules_pass(self):
        self.assertEqual(_schema_findings(FOUCAULT_RULES), [])

    def test_unknown_rule_key_is_reported(self):
        self.assertTrue(any("finding_rules" in item for item in _schema_findings({"regex": "x"})))

    def test_keys_must_include_file_and_line(self):
        self.assertTrue(any("file" in item for item in _schema_findings({"keys": ["title"]})))

    def test_severities_must_be_strings(self):
        self.assertTrue(any("severities" in item for item in _schema_findings({"severities": [1]})))

    def test_rules_must_be_an_object(self):
        self.assertTrue(any("finding_rules" in item for item in _schema_findings(["keys"])))


class FindingRulesEnforcementTest(unittest.TestCase):
    """The validator enforces the declared finding rules."""

    def validate(self, findings: list):
        return validator.validate_response(_response(findings), "PR", FOUCAULT_RULES)

    def test_valid_finding_passes(self):
        self.assertEqual(self.validate([_finding()])[0], "BLOCK")

    def test_extra_key_is_rejected(self):
        with self.assertRaisesRegex(validator.ResponseError, "keys"):
            self.validate([_finding(confidence="likely")])

    def test_missing_key_is_rejected(self):
        finding = _finding()
        del finding["title"]
        with self.assertRaisesRegex(validator.ResponseError, "keys"):
            self.validate([finding])

    def test_unknown_severity_is_rejected(self):
        with self.assertRaisesRegex(validator.ResponseError, "severity"):
            self.validate([_finding(severity="EXTREME")])

    def test_class_outside_prefix_is_rejected(self):
        with self.assertRaisesRegex(validator.ResponseError, "class"):
            self.validate([_finding(**{"class": "3.1"})])

    def test_class_with_non_numeric_suffix_is_rejected(self):
        with self.assertRaisesRegex(validator.ResponseError, "class"):
            self.validate([_finding(**{"class": "2.x"})])

    def test_no_rules_keeps_the_generic_check(self):
        verdict, _payload = validator.validate_response(_response([_finding(severity="EXTREME")]), "PR")
        self.assertEqual(verdict, "BLOCK")


if __name__ == "__main__":
    unittest.main()

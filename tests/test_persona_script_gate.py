#!/usr/bin/env python3
"""The command gate recognizes the persona eval and checker scripts in hooks/workflow-scripts.txt."""

import unittest

from tests.test_command_execution_gate import _load_gate_module
from tests.test_enforce_branch_name import REPO_ROOT

PROJECT_DIR = str(REPO_ROOT)
ADAPTER = "engine.call_model:call_model"
ALLOWED_PERSONA_COMMANDS = (
    "python engine/run_eval.py --persona euler",
    "python engine/run_eval.py --persona generay --mode file",
    "python engine/run_eval.py --persona foucault --case sql-injection",
    "python reviewers/euler/scripts/check_quality_policy.py reviewers/euler/QUALITY.md",
    "python reviewers/euler/scripts/check_quality_policy.py reviewers/euler/QUALITY.md --prose-only",
    "python reviewers/euler/scripts/check_code_quality.py all engine/",
    "python reviewers/euler/scripts/check_code_quality.py all engine/ reviewers/",
    "python reviewers/foucault/scripts/check_audit_policy.py reviewers/foucault/AUDIT.md",
    "python reviewers/generay/scripts/check_doc_policy.py reviewers/generay/TIME.md",
    "python reviewers/generay/scripts/check_doc_policy.py reviewers/generay/SYNC.md --prose-only",
    "python reviewers/generay/scripts/check_ledger_coverage.py --root reviewers/generay",
    "python reviewers/generay/scripts/check_time_handling.py all engine/",
    "python reviewers/generay/scripts/validate_registry.py",
)
CONSENT_MODEL_COMMANDS = (
    f"python engine/run_eval.py --persona euler --model-call {ADAPTER}",
    f"python engine/run_eval.py --persona euler --mode file --model-call {ADAPTER}",
    f"python engine/run_eval.py --persona generay --model-call {ADAPTER} --repeat 5",
    f"python engine/run_eval.py --persona generay --mode file --model-call {ADAPTER} --repeat 3",
)
UNLISTED_COMMANDS = (
    "python engine/run_eval.py --persona euler --model-call mymodule:call_model",
    "python engine/run_eval.py --persona ../x",
    "python engine/run_eval.py --persona euler --root /etc",
    "python reviewers/generay/scripts/check_ledger_coverage.py --root /etc",
    "python engine/run_review.py --persona euler --mode quality",
    "python engine/run_hook.py",
    "python engine/path_filter.py",
    "python engine/review_key.py",
)


class PersonaScriptVerdictTest(unittest.TestCase):
    """Evals without a model and persona checkers pass. Model evals ask. Other forms stay unlisted."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = _load_gate_module()

    def decide(self, command: str) -> tuple:
        return self.gate.workflow_decision(command, PROJECT_DIR)

    def test_structure_evals_checkers_allowed(self) -> None:
        for command in ALLOWED_PERSONA_COMMANDS:
            with self.subTest(command=command):
                self.assertEqual(self.decide(command), ("allow", ""))

    def test_model_evals_route_to_consent(self) -> None:
        for command in CONSENT_MODEL_COMMANDS:
            with self.subTest(command=command):
                decision, reason = self.decide(command)
                self.assertEqual(decision, "ask")
                self.assertIn("execution consent", reason)

    def test_other_adapters_stay_unmatched(self) -> None:
        for command in UNLISTED_COMMANDS:
            with self.subTest(command=command):
                self.assertEqual(self.decide(command), ("", ""))


if __name__ == "__main__":
    unittest.main()

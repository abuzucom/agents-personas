#!/usr/bin/env python3
"""The command gate recognizes the review engine scripts listed in hooks/workflow-scripts.txt."""
import unittest

from tests.test_command_execution_gate import _load_gate_module
from tests.test_enforce_branch_name import REPO_ROOT

PROJECT_DIR = str(REPO_ROOT)
ALLOWED_ENGINE_COMMANDS = (
    "python engine/check_reviewers.py",
    "python engine/check_reviewers.py --root .",
    "python engine/render_context.py --persona generay --mode sync",
    "python engine/render_context.py --root . --persona generay --mode sync",
    "python engine/check_review_response.py out/response.txt",
    "python engine/check_review_response.py out/response.txt --mode PR",
)
CONSENT_ENGINE_COMMANDS = (
    "python engine/build_pr_case.py --persona euler --mode quality --base origin/main --head HEAD"
    " --pr-number 7 --out-dir out",
)
UNLISTED_ENGINE_COMMANDS = (
    "python engine/call_model.py",
    "python engine/run_model_command.py",
    "python engine/render_context.py --persona ../x --mode sync",
    "python engine/check_reviewers.py --root /etc",
)


class EngineScriptVerdictTest(unittest.TestCase):
    """Inspecting engine scripts pass. Writing ones ask. Provider callers stay unlisted."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = _load_gate_module()

    def decide(self, command: str) -> tuple:
        return self.gate.workflow_decision(command, PROJECT_DIR)

    def test_inspecting_engine_scripts_are_allowed(self) -> None:
        for command in ALLOWED_ENGINE_COMMANDS:
            with self.subTest(command=command):
                self.assertEqual(self.decide(command), ("allow", ""))

    def test_envelope_builder_routes_to_consent(self) -> None:
        for command in CONSENT_ENGINE_COMMANDS:
            with self.subTest(command=command):
                decision, reason = self.decide(command)
                self.assertEqual(decision, "ask")
                self.assertIn("execution consent", reason)

    def test_provider_callers_and_unsafe_arguments_stay_unmatched(self) -> None:
        for command in UNLISTED_ENGINE_COMMANDS:
            with self.subTest(command=command):
                self.assertEqual(self.decide(command), ("", ""))


if __name__ == "__main__":
    unittest.main()

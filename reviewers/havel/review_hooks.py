"""havel review hooks for the engine: the AUDIT.md section 6 reply rule.

engine/run_review.py calls validate_reply on each reply. havel defines no
case_context, so the model receives no repository file beyond the diff.
havel defines no forced_verdict. The engine verdict rules already cover
every havel escalation.
"""

from __future__ import annotations

import sys
from pathlib import Path

PERSONA_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PERSONA_DIR / "scripts"))

import legal_notice  # resolved through the path set above

REVIEW_VERDICT_LABEL = "VERDICT"


def validate_reply(payload: dict, response: str, envelope: dict) -> list[str]:
    """Return the section 6 disclaimer problem of one review reply."""
    del payload, envelope
    problem = legal_notice.disclaimer_problem(response, REVIEW_VERDICT_LABEL)
    return [problem] if problem else []

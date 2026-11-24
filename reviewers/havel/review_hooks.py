"""havel review hooks for the engine: the scope check and the section 6 reply rule.

engine/build_pr_case.py calls case_context in the build stage, which holds
no provider key. The hook checks the trusted regimes option against
docs/regimes/scope-profiles.md. Only profile names, slugs, the reserved word
undeclared, and the empty value reach TRUSTED_CONTEXT. An unknown name or a
blank entry stops the build before any envelope exists. The hook adds no
review target context, so the model receives no repository file beyond the
diff.

engine/run_review.py calls validate_reply on each reply. havel defines no
forced_verdict. The engine verdict rules already cover every havel
escalation.
"""

from __future__ import annotations

import sys
from pathlib import Path

PERSONA_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PERSONA_DIR / "scripts"))

import check_regime_refs  # resolved through the path set above
import legal_notice  # resolved through the path set above

REVIEW_VERDICT_LABEL = "VERDICT"
PROFILES = check_regime_refs.load_profiles(PERSONA_DIR)


def check_regimes(regimes: str) -> None:
    """Raise ValueError unless an empty value or every listed name is a known scope."""
    if not regimes.strip():
        return
    names = [part.strip() for part in regimes.split(",")]
    if not all(names):
        raise ValueError("regimes holds a blank entry. List profile names or slugs separated by single commas.")
    # expand_scope raises ScopeError, a ValueError, for an unknown name.
    check_regime_refs.expand_scope(names, PROFILES)


def case_context(head_dir: Path, changed: list[str], patches: dict[str, str], options: dict) -> dict:
    """Check the trusted regimes option and return an empty context."""
    del head_dir, changed, patches
    check_regimes(options["regimes"])
    return {"context": {}, "unreviewed": []}


def validate_reply(payload: dict, response: str, envelope: dict) -> list[str]:
    """Return the section 6 disclaimer problem of one review reply."""
    del payload, envelope
    problem = legal_notice.disclaimer_problem(response, REVIEW_VERDICT_LABEL)
    return [problem] if problem else []

"""generay review hooks for the engine: the time prescan and the TIME.md reply rules.

engine/build_pr_case.py calls case_context in the build stage, which holds
no provider key. engine/run_review.py calls validate_reply on each reply.
generay defines no forced_verdict. Every time check is advisory, and the
engine already forbids APPROVE with unreviewed files.
"""

from __future__ import annotations

import sys
from pathlib import Path

PERSONA_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PERSONA_DIR / "scripts"))

import time_prescan  # resolved through the path set above
import time_reply  # resolved through the path set above

CHECKS = time_reply.load_checks()


def case_context(head_dir: Path, changed: list[str], patches: dict[str, str], options: dict) -> dict:
    """Return the prescan candidates and the files that exhaust the parsers."""
    items, unparsed = time_prescan.build_prescan(Path(head_dir), changed, patches,
                                                 options["exclude_paths"].split())
    return {"context": {"prescan": items}, "unreviewed": unparsed}


def validate_reply(payload: dict, response: str, envelope: dict) -> list[str]:
    """Return every TIME.md and SYNC.md problem in one reply."""
    del payload
    context = time_reply.context_from_envelope(envelope, time_reply.unreviewed_from_envelope(envelope))
    return time_reply.validate(response, context, CHECKS)

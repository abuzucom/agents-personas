"""euler review hooks for the engine: the prescan, the QUALITY.md reply rules, and prescan BLOCK.

engine/build_pr_case.py calls case_context in the build stage, which holds
no provider key. engine/run_review.py calls validate_reply on each reply and
forced_verdict on the run.
"""

from __future__ import annotations

import sys
from pathlib import Path

PERSONA_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PERSONA_DIR / "scripts"))

import prescan  # resolved through the path set above
import quality_reply  # resolved through the path set above

POLICY_PATH = PERSONA_DIR / "QUALITY.md"
# The pull request review mode answers as QUALITY.md mode PR.
REVIEW_MODE = "PR"
CLASSES = quality_reply.load_classes(POLICY_PATH)


def case_context(head_dir: Path, changed: list[str], patches: dict[str, str], options: dict) -> dict:
    """Return the prescan candidates and the files that exhaust the parsers."""
    items, unparsed = prescan.build_prescan(Path(head_dir), changed, patches, options["exclude_paths"].split())
    return {"context": {"prescan": items}, "unreviewed": unparsed}


def review_context(envelope: dict) -> quality_reply.ReviewContext:
    """Return the facts a reply must agree with for one engine envelope."""
    target = envelope["REVIEW_TARGET"]
    return quality_reply.ReviewContext(
        REVIEW_MODE,
        set(target["files"]),
        {item["id"] for item in target.get("prescan", [])},
        target.get("unreviewed", []),
    )


def validate_reply(payload: dict, response: str, envelope: dict) -> list[str]:
    """Return every QUALITY.md problem in one reply."""
    del payload
    return quality_reply.validate(response, review_context(envelope), CLASSES)


def forced_verdict(context: dict) -> tuple[str, str] | None:
    """Return BLOCK when a blocking prescan check reported a candidate."""
    classes = sorted({item["class"] for item in context.get("prescan", []) if item.get("blocking")})
    if not classes:
        return None
    # Class IDs come from the checker. File paths stay out of the reason
    # because the comment renders reasons outside a fence.
    return "BLOCK", f"blocking prescan finding in class {', '.join(classes)}"

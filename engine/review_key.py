#!/usr/bin/env python3
"""Compute the cache key of one persona review.

The review workflow stores this key in the external_id of the check run it
publishes. A rerun with the same key reuses that check run and calls no
model. One head therefore gets one model verdict per input set. The key covers
every input that changes the review: the persona, the mode, both commits,
the engine ref, the pull request title and body, the persona options, the
chunk caps, the model call command, and the fail_on_block gate. The digest
holds no pull request text.

The CLI reads the fields from the environment and appends key=<value> to
GITHUB_OUTPUT.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

KEY_VERSION = "review-v1"
KEY_FIELDS = ("PERSONA", "MODE", "HEAD_SHA", "BASE_SHA", "PERSONAS_REF", "PR_TITLE", "PR_BODY",
              "PERSONA_OPTIONS", "MAX_CHUNKS", "MAX_ENVELOPE_BYTES", "MODEL_CALL_COMMAND", "FAIL_ON_BLOCK")


class ReviewKeyError(ValueError):
    """A key input that is missing."""


def review_key(fields: dict[str, str]) -> str:
    """Return the versioned SHA-256 key of one review input set."""
    missing = [name for name in KEY_FIELDS if name not in fields]
    if missing:
        raise ReviewKeyError(f"missing key field(s): {', '.join(missing)}")
    # JSON encoding keeps each field boundary, so text cannot move between
    # the title and the body without changing the digest.
    canonical = json.dumps([fields[name] for name in KEY_FIELDS], ensure_ascii=True, separators=(",", ":"))
    return f"{KEY_VERSION}:{hashlib.sha256(canonical.encode('ascii')).hexdigest()}"


def main() -> int:
    """Append the key of the environment fields to GITHUB_OUTPUT."""
    try:
        key = review_key({name: os.environ[name] for name in KEY_FIELDS if name in os.environ})
        output_path = os.environ["GITHUB_OUTPUT"]
    except (ReviewKeyError, KeyError) as error:
        print(f"error: cannot compute the review key: {error}. Set every key field.", file=sys.stderr)
        return 1
    with Path(output_path).open("a", encoding="utf-8") as output:
        output.write(f"key={key}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""adorno grading beyond the engine core, loaded by engine/run_eval.py.

The checks match the standalone adorno eval runner and corpus tests at
revision 97a2c84:
- expected.json carries an expected_classes list. Every entry names an
  AUDIT.md section 2 class heading.
- notes is a non-empty string.
- allow_non_ascii: true needs non-empty fixture_notes that state the reason.
- A case holds at least one input file the adorno runner reads.

The engine core grades the verdict line and the VERDICT_JSON companion.
"""

from __future__ import annotations

import re
from pathlib import Path

PERSONA_DIR = Path(__file__).resolve().parent.parent
CLASS_HEADING = re.compile(r"^### (2\.\d+)", re.MULTILINE)
KNOWN_CLASSES = frozenset(CLASS_HEADING.findall((PERSONA_DIR / "AUDIT.md").read_text(encoding="utf-8")))
# The input names the adorno runner reads, in its read order.
CASE_INPUT_NAMES = (
    "diff.patch",
    "input.jsx",
    "input.tsx",
    "input.tsx.txt",
    "input.js",
    "input.ts",
    "input.py",
    "input.html",
    "input.css",
    "input.md",
    "input.txt",
    "spec.md",
    "tokens.json",
)


def validate_expected(mode: str, expected: dict) -> list[str]:
    """Return adorno structure problems for one expected.json."""
    del mode
    if "expected_classes" not in expected:
        return ["missing key 'expected_classes'"]
    problems = []
    classes = expected["expected_classes"]
    if isinstance(classes, list):
        # A list or object entry is unhashable. The string test keeps the set lookup safe.
        for item in classes:
            if not isinstance(item, str):
                problems.append(f"expected_classes entries must be strings: {item!r}")
            elif item not in KNOWN_CLASSES:
                problems.append(f"unknown class '{item}' in expected_classes")
    else:
        problems.append("expected_classes must be a list")
    if not isinstance(expected.get("notes"), str) or not expected["notes"].strip():
        problems.append("notes must be a non-empty string")
    notes = expected.get("fixture_notes")
    # A blank reason explains nothing. A non-ASCII fixture needs real text.
    if expected.get("allow_non_ascii") and not (isinstance(notes, str) and notes.strip()):
        problems.append("allow_non_ascii: true requires fixture_notes explaining why")
    return problems


def validate_case(case: dict) -> list[str]:
    """Return a problem when the case holds no input the adorno runner reads."""
    if any(name in CASE_INPUT_NAMES for name in case["files"]):
        return []
    return ["no recognized input file present: " + ", ".join(case["files"])]

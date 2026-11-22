#!/usr/bin/env python3
"""Validate the review response contract shared by every persona and mode.

Ported from `abuzucom/foucault` `scripts/check_pr_review_response.py`. The
engine checks the parts every persona shares: the final verdict lines, the
JSON payload, and the location of each finding. Persona-specific finding
fields such as severity and class stay with the persona.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

VERDICTS = ("APPROVE", "BLOCK", "NEEDS-HUMAN")
VERDICT_PATTERN = re.compile(r"^VERDICT:\s*(APPROVE|BLOCK|NEEDS-HUMAN)(?:\s+-\s+.*)?$")
VERDICT_PREFIX = "VERDICT:"
VERDICT_JSON_PREFIX = "VERDICT_JSON:"
REQUIRED_JSON_KEYS = frozenset({"verdict", "findings"})
RESPONSE_LIMIT = 1_000_000
# A bare "i" or "we" opener is narration unless a period follows, as in
# "i.e.". Section labels such as "Trace:" or "Inspect results:" are
# impersonal. Narration with those verbs starts with "I", "we", or "let me".
PROCESS_NARRATION_PATTERNS = (
    re.compile(r"^\s*(?:(?:[-*+])\s+|\d+[.)]\s+)?(?:i|we)\b(?!\.)", re.IGNORECASE),
    re.compile(
        r"^\s*(?:(?:[-*+])\s+|\d+[.)]\s+)?(?:let me\b|let's\b|"
        r"should i\b|could i\b|would i\b|"
        r"do i\b|did i\b|am i\b|have i\b|wait(?:,|\s|$)|"
        r"actually(?:,|\s|$)|on second thought\b|reconsider(?:ing)?\b|"
        r"check whether\b|check if\b|"
        r"now i\b|first i\b|what if\b|maybe (?:i|we)\b|"
        r"perhaps (?:i|we)\b|should (?:this|that|it|the)\b|"
        r"could (?:this|that|it)\b|would (?:this|that|it)\b|"
        r"is this\b|does this\b)",
        re.IGNORECASE,
    ),
    # A coverage sentence such as "Reviewed all 18 changed files" narrates the
    # review. The report states coverage in the noun-only Scope: and Unseen:
    # lines instead.
    re.compile(
        r"^\s*(?:(?:[-*+])\s+|\d+[.)]\s+)?(?:reviewed|examined|inspected|traced|checked|analyzed|"
        r"verified|looked|went|started|review covered|the review)\b",
        re.IGNORECASE,
    ),
)


# A mode with require_coverage opens its report with these three lines. The
# mode line holds only the mode value. Scope: and Unseen: each hold a noun
# list. The check reads structure only and never judges the nouns.
MODE_LINE_PATTERN = re.compile(r"^(?:\*\*Mode:\*\*|Mode:)[ \t]*(\S+)[ \t]*$")
COVERAGE_LABELS = ("Scope:", "Unseen:")


class ResponseError(ValueError):
    """Report a response-contract failure."""


class NarrationError(ResponseError):
    """Report process narration in an otherwise checked response."""


class CoverageError(NarrationError):
    """Report missing or malformed coverage lines in an otherwise checked response."""


def _verdict_indexes(lines: list[str]) -> list[int]:
    """Return the indexes of every line that starts with VERDICT: at column zero."""
    return [index for index, line in enumerate(lines) if line.startswith(VERDICT_PREFIX)]


def _last_verdict(lines: list[str]) -> str:
    """Return the verdict from the line the workflow gate reads.

    The gate reads the last newline-delimited line that starts with
    VERDICT: at column zero. Splitting on newline alone matches that gate.
    splitlines() also breaks on carriage returns and form feeds.
    """
    if not any(line.strip() for line in lines):
        raise ResponseError("response is empty")
    indexes = _verdict_indexes(lines)
    if not indexes:
        raise ResponseError("no VERDICT line at column zero")
    match = VERDICT_PATTERN.fullmatch(lines[indexes[-1]].rstrip())
    if not match:
        raise ResponseError("final VERDICT line is malformed")
    return match.group(1)


def _parse_json_line(lines: list[str]) -> dict[str, Any]:
    """Return the VERDICT_JSON object and check its position."""
    json_indexes = [index for index, line in enumerate(lines) if line.startswith(VERDICT_JSON_PREFIX)]
    if not json_indexes:
        raise ResponseError("no VERDICT_JSON line")
    json_index = json_indexes[-1]
    try:
        payload = json.loads(lines[json_index][len(VERDICT_JSON_PREFIX) :].lstrip())
    except json.JSONDecodeError as error:
        raise ResponseError("VERDICT_JSON is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ResponseError("VERDICT_JSON is not an object")
    nonempty = [index for index, line in enumerate(lines) if line.strip()]
    if nonempty[-1] != json_index:
        raise ResponseError("VERDICT_JSON must be the final report line")
    if json_index != _verdict_indexes(lines)[-1] + 1:
        raise ResponseError("VERDICT_JSON must immediately follow the final VERDICT line")
    return payload


def process_narration_lines(response: str) -> list[int]:
    """Return line numbers with clear first-person process narration."""
    lines = response.split("\n")
    indexes = _verdict_indexes(lines)
    if not indexes:
        return []
    narration = []
    fenced = False
    for index, line in enumerate(lines[: indexes[-1]]):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if fenced or stripped.startswith(">"):
            continue
        if any(pattern.match(line) for pattern in PROCESS_NARRATION_PATTERNS):
            narration.append(index + 1)
    return narration


def coverage_problem(lines: list[str], expected_mode: str | None = None) -> str:
    """Return why the report opening breaks the coverage contract, or an empty string."""
    opening = [line.strip() for line in lines if line.strip()][: len(COVERAGE_LABELS) + 1]
    match = MODE_LINE_PATTERN.match(opening[0]) if opening else None
    if match is None:
        return "the first coverage line must be the mode line with nothing after the mode value"
    if expected_mode is not None and match.group(1) != expected_mode:
        return f"the first coverage line must name mode {expected_mode}, not {match.group(1)}"
    for index, label in enumerate(COVERAGE_LABELS, start=1):
        line = opening[index] if index < len(opening) else ""
        if not line.startswith(label) or not line[len(label) :].strip():
            return f"coverage line {index + 1} must start with {label} and list nouns"
    return ""


def _validate_finding(finding: Any) -> None:
    """Require the file and line every annotation needs."""
    if not isinstance(finding, dict):
        raise ResponseError("finding must be a JSON object")
    if not isinstance(finding.get("file"), str) or not finding["file"]:
        raise ResponseError("finding has an invalid file")
    line = finding.get("line")
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        raise ResponseError("finding has an invalid line")


def _validate_finding_rules(finding: dict[str, Any], rules: dict[str, Any]) -> None:
    """Enforce one persona's declared finding fields."""
    keys = rules.get("keys")
    if keys is not None and set(finding) != set(keys):
        raise ResponseError(f"finding keys {sorted(finding)} differ from the declared keys {sorted(keys)}")
    severities = rules.get("severities")
    if severities is not None and finding.get("severity") not in severities:
        raise ResponseError("finding has an invalid severity")
    prefix = rules.get("class_prefix")
    if prefix is None:
        return
    value = finding.get("class")
    suffix = value[len(prefix) :] if isinstance(value, str) and value.startswith(prefix) else ""
    if not (suffix.isascii() and suffix.isdigit()):
        raise ResponseError(f"finding class must be '{prefix}' followed by digits")


def _validate_payload(
    payload: dict[str, Any], verdict: str, expected_mode: str | None, finding_rules: dict[str, Any] | None = None
) -> None:
    """Check the payload keys, verdict, mode, and findings."""
    missing = sorted(REQUIRED_JSON_KEYS - set(payload))
    if missing:
        raise ResponseError(f"VERDICT_JSON lacks {', '.join(missing)}")
    if payload["verdict"] != verdict:
        raise ResponseError("VERDICT_JSON verdict does not match the VERDICT line")
    if expected_mode is not None and payload.get("mode") != expected_mode:
        raise ResponseError(f"VERDICT_JSON mode '{payload.get('mode')}' does not match expected mode '{expected_mode}'")
    findings = payload["findings"]
    if not isinstance(findings, list):
        raise ResponseError("VERDICT_JSON findings is not a list")
    for finding in findings:
        _validate_finding(finding)
        if finding_rules:
            _validate_finding_rules(finding, finding_rules)


def validate_response(
    response: str,
    expected_mode: str | None = None,
    finding_rules: dict[str, Any] | None = None,
    allow_narration: bool = False,
    require_coverage: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Validate one bounded review response and return its verdict and JSON.

    require_coverage checks the Mode, Scope, and Unseen opening lines.
    allow_narration skips the narration and coverage checks. The engine uses
    it to keep the findings of a reply that still fails them after its retry.
    """
    if len(response.encode("utf-8")) > RESPONSE_LIMIT:
        raise ResponseError("response exceeds the configured limit")
    lines = response.split("\n")
    verdict = _last_verdict(lines)
    payload = _parse_json_line(lines)
    _validate_payload(payload, verdict, expected_mode, finding_rules)
    narration = [] if allow_narration else process_narration_lines(response)
    if narration:
        numbers = ", ".join(str(number) for number in narration[:5])
        raise NarrationError(f"process narration appears on report line(s): {numbers}")
    problem = coverage_problem(lines, expected_mode) if require_coverage and not allow_narration else ""
    if problem:
        raise CoverageError(problem)
    return verdict, payload


def main(argv: list[str]) -> int:
    """Validate one response file and print the normalized verdict."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("response", type=Path)
    parser.add_argument("--mode", help="mode value VERDICT_JSON must carry")
    options = parser.parse_args(argv)
    try:
        # read_text() turns a bare carriage return into a newline. The gate
        # keeps it inside one line, so decode the raw bytes instead.
        response = options.response.read_bytes().decode("utf-8")
        verdict, _payload = validate_response(response, options.mode)
    except (OSError, UnicodeError, ResponseError) as error:
        print(f"invalid review response: {error}. Fix the model output contract and rerun.", file=sys.stderr)
        return 1
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

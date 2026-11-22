#!/usr/bin/env python3
"""Validate a model review report against QUALITY.md tiers and the envelope.

A report passes only with one final line, a matching VERDICT_JSON, known
classes, tier-consistent severities and verdict, changed-file locations, and
a resolution for every prescan item.

Ported from `abuzucom/euler` `ci/check_review_response.py` at 9488a8c. The
engine already owns a module named check_review_response, so this copy
carries another name. REPO_ROOT names the persona directory here.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_quality_policy  # resolved through the path set above
import review_report  # resolved through the path set above

SCHEMA_VERSION = "1"
SEVERITIES = ("HIGH", "MEDIUM", "LOW")
CONFIDENCES = ("certain", "likely")
PRESCAN_STATUSES = ("confirmed", "dismissed")
VERDICT_RANK = {"APPROVE": 0, "NEEDS-HUMAN": 1, "BLOCK": 2}
# A missing new-side count means one line, as in git's unified diff.
HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


@dataclass(frozen=True)
class ReviewContext:
    """Envelope facts the report must agree with."""

    mode: str
    changed_files: set[str]
    prescan_ids: set[str]
    unreviewed: list[str]
    # Line ranges a finding may cite, keyed by file. A file without an
    # entry carries no line check.
    line_ranges: dict[str, tuple[range, ...]] = field(default_factory=dict)


def load_classes(policy_path: Path) -> dict[str, check_quality_policy.PolicyClass]:
    """Return the QUALITY.md classes keyed by ID."""
    return check_quality_policy.parse_classes(policy_path.read_text(encoding="ascii"))


def finding_problems(item: object, context: ReviewContext, classes: dict) -> list[str]:
    """Return problems for one VERDICT_JSON finding."""
    if not isinstance(item, dict):
        return ["finding must be a JSON object"]
    problems = []
    class_id, severity = item.get("class"), item.get("severity")
    # Model output is untrusted JSON. A list or object here is unhashable and
    # would crash the dict lookup below instead of failing validation.
    if not isinstance(class_id, str):
        problems.append("finding class must be a string")
        policy_class = None
    else:
        policy_class = classes.get(class_id)
        if policy_class is None:
            problems.append(f"unknown class {class_id}")
    if severity not in SEVERITIES:
        problems.append(f"finding severity must be one of {', '.join(SEVERITIES)}")
    elif policy_class and policy_class.tier == "Advisory" and severity != "LOW":
        problems.append(f"advisory class {class_id} rated {severity}, ceiling is LOW")
    if item.get("confidence") not in CONFIDENCES:
        problems.append("finding confidence must be certain or likely")
    return problems + location_problems(item.get("file"), item.get("line"), context)


def location_problems(cited_file: object, line: object, context: ReviewContext) -> list[str]:
    """Return problems with the file and line one finding cites.

    A finding cites a file and line in the review target. A PR line falls
    inside a hunk of the file patch. A local line falls inside the file.
    """
    if not isinstance(cited_file, str):
        problems = ["finding file must be a string"]
    elif cited_file in context.changed_files:
        problems = []
    elif context.mode == "PR":
        problems = [f"finding cites {cited_file} outside the changed files"]
    else:
        problems = [f"finding cites {cited_file!r} outside the review target"]
    if isinstance(line, bool) or not isinstance(line, int) or line < 1:
        return problems + ["finding line must be a positive integer"]
    ranges = context.line_ranges.get(cited_file) if isinstance(cited_file, str) else None
    if ranges is not None and not any(line in span for span in ranges):
        problems.append(f"finding line {line} is outside the review target for {cited_file}")
    return problems


def hunk_ranges(patch: str) -> tuple[range, ...]:
    """Return the new-side line range of every hunk in one patch."""
    spans = []
    for text in patch.splitlines():
        header = HUNK_HEADER.match(text)
        if header is None:
            continue
        start = int(header.group("start"))
        count = int(header.group("count") or 1)
        spans.append(range(start, start + count))
    return tuple(spans)


def required_verdict(findings: list[dict], classes: dict) -> str:
    """Return the minimum verdict the tiers demand."""
    tiers = [
        (classes[item["class"]].tier, item.get("severity"))
        for item in findings
        if isinstance(item.get("class"), str) and item["class"] in classes
    ]
    if any(tier == "Blocking" or (tier == "Graded" and severity == "HIGH") for tier, severity in tiers):
        return "BLOCK"
    if any(tier == "Escalate" for tier, _ in tiers):
        return "NEEDS-HUMAN"
    return "APPROVE"


def verdict_problems(verdict: str, findings: list[dict], context: ReviewContext, classes: dict) -> list[str]:
    """Return problems where the verdict disagrees with tiers or coverage."""
    required = required_verdict([item for item in findings if isinstance(item, dict)], classes)
    problems = []
    if verdict not in VERDICT_RANK:
        return [f"unknown verdict token {verdict}"]
    if required == "BLOCK" and verdict != "BLOCK":
        problems.append(f"verdict {verdict} conflicts with tiers, expected BLOCK")
    elif required == "NEEDS-HUMAN" and verdict != "NEEDS-HUMAN":
        problems.append(f"verdict {verdict} conflicts with tiers, expected NEEDS-HUMAN")
    elif required == "APPROVE" and verdict == "BLOCK":
        problems.append("verdict BLOCK conflicts with tiers, expected APPROVE or NEEDS-HUMAN")
    if context.unreviewed and verdict == "APPROVE":
        problems.append("unreviewed files forbid APPROVE")
    return problems


def prescan_problems(entries: object, context: ReviewContext) -> list[str]:
    """Return problems in the prescan resolution array."""
    if not isinstance(entries, list):
        return ["VERDICT_JSON prescan must be an array"]
    resolved = set()
    problems = []
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("id"), str)
            or entry.get("status") not in PRESCAN_STATUSES
            or not entry.get("reason")
        ):
            problems.append("prescan entries need an id, a confirmed or dismissed status, and a reason")
            continue
        resolved.add(entry.get("id"))
    problems.extend(f"prescan item {item} lacks a resolution" for item in sorted(context.prescan_ids - resolved))
    return problems


def validate(text: str, context: ReviewContext, classes: dict) -> list[str]:
    """Return every problem in one report. An empty list means valid."""
    report = review_report.parse_report(text)
    problems = []
    if review_report.contains_process_narration(text):
        problems.append("report contains process narration")
    if context.mode == "PR" and (report.label != "VERDICT" or report.final_line_count != 1):
        problems.append(f"expected exactly one final VERDICT line, found {report.final_line_count}")
    if report.payload is None:
        return problems + [report.json_error or "missing VERDICT_JSON"]
    payload = report.payload
    if payload.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"VERDICT_JSON schema_version must be '{SCHEMA_VERSION}'")
    if payload.get("verdict") != report.token:
        problems.append(f"VERDICT_JSON verdict '{payload.get('verdict')}' differs from final line '{report.token}'")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return problems + ["VERDICT_JSON findings must be an array"]
    for item in findings:
        problems.extend(finding_problems(item, context, classes))
    if context.mode == "PR" and report.token:
        problems.extend(verdict_problems(report.token, findings, context, classes))
    problems.extend(prescan_problems(payload.get("prescan", []), context))
    return problems


def is_engine_envelope(envelope: dict) -> bool:
    """Return True for an agents-personas engine envelope.

    The engine names the persona in TRUSTED_CONTEXT and keeps the prescan
    and the unreviewed paths in REVIEW_TARGET. The euler envelope of the
    eval runner keeps both in TRUSTED_CONTEXT.
    """
    return "persona" in envelope.get("TRUSTED_CONTEXT", {})


def unreviewed_from_envelope(envelope: dict) -> list[str]:
    """Return the unreviewed paths that one envelope records."""
    if is_engine_envelope(envelope):
        return envelope["REVIEW_TARGET"].get("unreviewed", [])
    return envelope["TRUSTED_CONTEXT"].get("metadata", {}).get("unreviewed", [])


def context_from_envelope(envelope: dict, unreviewed: list[str]) -> ReviewContext:
    """Return the validation context for one envelope."""
    target = envelope["REVIEW_TARGET"]
    files = target["files"]
    if is_engine_envelope(envelope):
        # The engine quality mode answers as QUALITY.md mode PR.
        mode, prescan = "PR", target.get("prescan", [])
    else:
        mode, prescan = envelope["mode"], envelope["TRUSTED_CONTEXT"].get("prescan", [])
    # A PR target holds patch text. A local target holds whole files.
    if mode == "PR":
        line_ranges = {name: hunk_ranges(text) for name, text in files.items()}
    else:
        line_ranges = {name: (range(1, len(text.splitlines()) + 1),) for name, text in files.items()}
    return ReviewContext(mode, set(files), {item["id"] for item in prescan}, unreviewed, line_ranges)


def main() -> int:
    """Validate one report file against one envelope file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("envelope", type=Path)
    parser.add_argument("--policy", type=Path, default=REPO_ROOT / "QUALITY.md")
    args = parser.parse_args()
    envelope = json.loads(args.envelope.read_text(encoding="utf-8"))
    # build_pr_case records the unreviewed files in each envelope. run_review
    # passes the same list. The CLI and the pipeline enforce one rule.
    context = context_from_envelope(envelope, unreviewed_from_envelope(envelope))
    problems = validate(args.report.read_text(encoding="utf-8"), context, load_classes(args.policy))
    for problem in problems:
        sys.stderr.write(f"error: {problem}\n")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

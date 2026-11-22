#!/usr/bin/env python3
"""Render one mode result as a check run, annotations, a comment, and metrics.

The workflow publishes the rendered JSON as written. Every decision about the
conclusion, the header line, and the caps lives here, where tests reach it.
"""

import argparse
import json
import re
import sys
from pathlib import Path

VERDICT_RANK = {"APPROVE": 0, "NEEDS-HUMAN": 1, "BLOCK": 2}
# GitHub accepts at most 50 annotations per check run update.
MAX_ANNOTATIONS = 50
MAX_ANNOTATION_MESSAGE_CHARS = 1000
# GitHub caps a comment body at 65,536 characters. The margin covers the header.
MAX_COMMENT_CHARS = 60_000
TRUNCATION_NOTE = "\n\n[Report truncated by the review engine.]"
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
SEVERITY_LEVELS = {"CRITICAL": "failure", "HIGH": "failure", "MEDIUM": "warning"}
FLAG_VALUES = {"true": True, "false": False}
# The workflow prints this line as a ::warning annotation. A fixed template
# and a validated check name keep workflow command syntax out of it.
NEEDS_HUMAN_WARNING = "{check} needs a human review. The check concludes neutral and blocks no merge."


def combine_verdicts(verdicts: list[str], unreviewed: list[str]) -> tuple[str, list[str]]:
    """Return the run verdict and its reasons from the chunk verdicts.

    The most severe chunk verdict wins. Unreviewed files forbid APPROVE.
    """
    unknown = sorted(set(verdicts) - set(VERDICT_RANK))
    if unknown:
        raise ValueError(f"unknown verdict values {unknown}")
    reasons = []
    if verdicts:
        verdict = max(verdicts, key=VERDICT_RANK.__getitem__)
    else:
        verdict = "APPROVE"
        reasons.append("no reviewable text changes")
    if unreviewed and verdict == "APPROVE":
        verdict = "NEEDS-HUMAN"
        reasons.append(f"{len(unreviewed)} unreviewed file(s) forbid APPROVE")
    return verdict, reasons


def conclusion(verdict: str, fail_on_block: bool) -> str:
    """Return the check conclusion for a verdict (decision 21).

    NEEDS-HUMAN warns and never blocks. fail_on_block gates BLOCK only.
    """
    if verdict == "APPROVE":
        return "success"
    if verdict == "BLOCK" and fail_on_block:
        return "failure"
    return "neutral"


def warning(result: dict) -> str:
    """Return the run warning for a NEEDS-HUMAN result, or an empty string."""
    if result["verdict"] != "NEEDS-HUMAN":
        return ""
    return NEEDS_HUMAN_WARNING.format(check=check_name(result["persona"], result["mode"]))


def check_name(persona: str, mode: str) -> str:
    """Return the check run name branch protection can require."""
    return f"{persona} / {mode}"


def comment_header(persona: str, mode: str, head_sha: str, verdict: str) -> str:
    """Return the first comment line that identifies the run."""
    return f"{check_name(persona, mode)} | head {head_sha} | VERDICT: {verdict}"


def clean_text(text: object, limit: int) -> str:
    """Return model text without control characters and cut to limit."""
    cleaned = CONTROL_CHARACTERS.sub("", str(text))
    return cleaned[:limit]


def annotations(findings: list[dict], changed_files: list[str]) -> list[dict]:
    """Return annotations for findings on changed files, capped for one update."""
    changed = set(changed_files)
    items: list[dict] = []
    for finding in findings:
        if finding.get("file") not in changed or len(items) == MAX_ANNOTATIONS:
            continue
        line = finding["line"]
        items.append({
            "path": finding["file"],
            "start_line": line,
            "end_line": line,
            "annotation_level": SEVERITY_LEVELS.get(str(finding.get("severity")), "notice"),
            "message": clean_text(
                finding.get("title") or finding.get("message") or "finding", MAX_ANNOTATION_MESSAGE_CHARS
            ),
        })
    return items


def _count(value: object) -> str:
    """Return a usage count for display."""
    return "unknown" if value is None else str(value)


def summary(result: dict) -> str:
    """Return the check summary with run metrics."""
    usage = result.get("usage", {})
    lines = [
        f"Verdict: {result['verdict']}",
        f"Chunks: {result['chunks']}",
        f"Duration: {result.get('duration_seconds', 0)} s",
        f"Input tokens: {_count(usage.get('input_tokens'))}",
        f"Output tokens: {_count(usage.get('output_tokens'))}",
        f"Unreviewed files: {len(result.get('unreviewed', []))}",
    ]
    lines += [f"Reason: {reason}" for reason in result.get("reasons", [])]
    lines += [f"Clamped request: {name}" for name in result.get("clamped", [])]
    return "\n".join(lines)


def comment_marker(persona: str, mode: str, head_sha: str) -> str:
    """Return the hidden first comment line that identifies the run.

    GitHub renders no HTML comment. The workflow matches this line to skip
    a second comment for the same head and mode.
    """
    return f"<!-- persona-review: {check_name(persona, mode)} | head {head_sha} -->"


def fence_for(text: str) -> str:
    """Return a code fence longer than the longest backtick run in text.

    The report is model output shaped by the pull request. A longer fence
    stops markdown from rendering images, links, or mentions from it.
    """
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def chunk_sections(result: dict) -> list[str]:
    """Return one heading and fenced report per chunk."""
    chunks = result.get("chunk_results")
    if chunks is None:
        chunks = [
            {"name": f"{index:03d}", "verdict": result["verdict"], "report": report, "reason": ""}
            for index, report in enumerate(result.get("reports", []), 1)
        ]
    sections = []
    for chunk in chunks:
        lines = [f"### Chunk {chunk['name']}: {chunk['verdict']}", ""]
        report = chunk.get("report", "").strip()
        if report:
            fence = fence_for(report)
            lines += [fence, report, fence]
        else:
            lines.append(chunk.get("reason") or "No report.")
        sections.append("\n".join(lines))
    return sections


def comment_body(result: dict, run_url: str = "") -> str:
    """Return the euler-style comment: verdict heading, revisions, chunk reports."""
    title = f"{result['persona'].capitalize()} {result['mode']} review: {result['verdict']}"
    lines = [comment_marker(result["persona"], result["mode"], result["head_sha"]), f"## {title}", ""]
    base_sha = result.get("base_sha")
    lines.append(f"Base `{base_sha}`. Head `{result['head_sha']}`." if base_sha else f"Head `{result['head_sha']}`.")
    if run_url:
        lines.append(f"Workflow run: {run_url}")
    lines += [f"- {reason}" for reason in result.get("reasons", [])]
    body = "\n".join(lines) + "\n\n" + "\n\n".join(chunk_sections(result))
    if len(body) <= MAX_COMMENT_CHARS:
        return body
    return body[: MAX_COMMENT_CHARS - len(TRUNCATION_NOTE)] + TRUNCATION_NOTE


def render(result: dict, fail_on_block: bool, run_url: str = "") -> dict:
    """Return everything the workflow publishes for one mode."""
    return {
        "check_name": check_name(result["persona"], result["mode"]),
        "conclusion": conclusion(result["verdict"], fail_on_block),
        "title": f"VERDICT: {result['verdict']}",
        "summary": summary(result),
        "annotations": annotations(result.get("findings", []), result.get("changed_files", [])),
        "comment_body": comment_body(result, run_url),
        "warning": warning(result),
    }


def main(argv: list[str]) -> int:
    """Read result.json and write the rendered output JSON."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("result", type=Path)
    parser.add_argument("--fail-on-block", required=True, choices=sorted(FLAG_VALUES))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-url", default="", help="workflow run link for the comment")
    options = parser.parse_args(argv)
    try:
        result = json.loads(options.result.read_text(encoding="utf-8"))
        rendered = render(result, FLAG_VALUES[options.fail_on_block], options.run_url)
        options.out.write_text(json.dumps(rendered, indent=2) + "\n", encoding="utf-8", newline="\n")
    except (OSError, ValueError, KeyError) as error:
        print(f"error: cannot render review output ({error}). Rerun the review step.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

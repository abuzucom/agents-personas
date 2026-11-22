"""euler grading beyond the engine core, loaded by engine/run_eval.py.

The checks match the standalone euler eval runner at revision 9488a8c:
- expected.json carries expect_json, a non-empty notes string, and known
  QUALITY.md classes. Optional fields keep their types.
- A PR case holds diff.patch. Other cases hold an input.<ext> file.
- The model input is the euler envelope. Non-PR cases carry prescan
  candidates from the deterministic checks.
- Grading adds the euler final-line rule, process narration, and the
  reported classes.
"""

from __future__ import annotations

import sys
from pathlib import Path

PERSONA_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PERSONA_DIR / "scripts"))

import check_quality_policy  # resolved through the path set above
import quality_checks  # resolved through the path set above
import review_envelope  # resolved through the path set above
import review_report  # resolved through the path set above

REVIEW_MODE = "quality"
KNOWN_CLASSES = frozenset(check_quality_policy.parse_classes((PERSONA_DIR / "QUALITY.md").read_text(encoding="ascii")))
RESERVED_FILES = frozenset({"expected.json", "context.md"})


def _optional_field_problems(expected: dict) -> list[str]:
    """Return problems in the optional expected.json fields."""
    problems = []
    elapsed = expected.get("active_work_elapsed_seconds")
    if elapsed is not None and (isinstance(elapsed, bool) or not isinstance(elapsed, int) or elapsed < 0):
        problems.append("active_work_elapsed_seconds must be a non-negative integer")
    review_status = expected.get("expected_review_status")
    if review_status is not None and review_status != "NEEDS-HUMAN":
        problems.append("expected_review_status must be NEEDS-HUMAN")
    if "forbid_process_narration" in expected and not isinstance(expected["forbid_process_narration"], bool):
        problems.append("forbid_process_narration must be a boolean")
    return problems


def validate_expected(mode: str, expected: dict) -> list[str]:
    """Return euler structure problems for one expected.json."""
    problems = [f"missing key '{key}'" for key in ("expected_classes", "expect_json") if key not in expected]
    if problems:
        return problems
    classes = expected["expected_classes"]
    if isinstance(classes, list):
        problems += [f"unknown class '{item}'" for item in classes if item not in KNOWN_CLASSES]
    if not isinstance(expected["expect_json"], bool):
        problems.append("expect_json must be a boolean")
    if not isinstance(expected.get("notes"), str) or not expected["notes"].strip():
        problems.append("notes must be a non-empty string")
    return problems + _optional_field_problems(expected)


def case_files(case: dict) -> dict[str, str]:
    """Return the review files of one case keyed by file name."""
    case_dir = Path(case["dir"])
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(case_dir.iterdir())
        if path.is_file() and path.name not in RESERVED_FILES
    }


def validate_case(case: dict) -> list[str]:
    """Return the euler fixture rule problems for one case."""
    names = case["files"]
    if case["mode"] == REVIEW_MODE:
        return [] if "diff.patch" in names else ["PR mode requires diff.patch"]
    return [] if any(name.startswith("input.") for name in names) else ["non-PR mode requires an input.<ext> file"]


def prescan_for(case: dict) -> list[dict]:
    """Return checker candidates for non-PR input files. PR cases carry no head tree."""
    if case["mode"] == REVIEW_MODE:
        return []
    case_dir = Path(case["dir"])
    inputs = [case_dir / name for name in case["files"] if name.startswith("input.")]
    findings = quality_checks.run_checks(list(quality_checks.CHECKS), inputs, case_dir)
    return [
        {"id": f"P{index}", "file": item.path, "line": item.line, "class": item.class_id, "message": item.message}
        for index, item in enumerate(findings, 1)
    ]


def build_model_input(case: dict, system_prompt: str) -> str:
    """Return the euler review envelope for one case."""
    del system_prompt
    metadata: dict[str, str | int] = {"source": "eval", "case": case["name"]}
    elapsed = case["expected"].get("active_work_elapsed_seconds")
    if elapsed is not None:
        metadata["active_work_elapsed_seconds"] = elapsed
    return review_envelope.build_envelope(
        case["prompt_mode"], case_files(case), case["context"], prescan_for(case), metadata
    )


def final_line_matches(case: dict, report: review_report.ParsedReport) -> bool:
    """Return True when the final line carries the expected verdict as a whole token."""
    expected_verdict = case["expected"]["expected_verdict"]
    if case["mode"] == REVIEW_MODE:
        return report.label == "VERDICT" and report.token == expected_verdict
    if expected_verdict == "NEEDS-HUMAN":
        # Piece mode allows NEEDS-HUMAN in place of a partial risk level.
        return report.token == expected_verdict
    final_line = f"{report.label}: {report.value}" if report.label else ""
    if not final_line.startswith(expected_verdict):
        return False
    remainder = final_line[len(expected_verdict) :]
    return not remainder or not (remainder[0].isalnum() or remainder[0] == "-")


def class_failures(findings: object, expected_classes: set[str]) -> list[str]:
    """Return mismatches between reported finding classes and the expected classes."""
    if not isinstance(findings, list):
        return ["VERDICT_JSON findings must be an array"]
    reported = {item["class"] for item in findings if isinstance(item, dict) and isinstance(item.get("class"), str)}
    missing = [f"missing expected class {item}" for item in sorted(expected_classes - reported)]
    return missing + [f"unexpected class {item}" for item in sorted(reported - expected_classes)]


def grade_response(case: dict, response: str) -> list[tuple[str, bool, str]]:
    """Return euler grades beyond the engine core."""
    report = review_report.parse_report(response)
    expected = case["expected"]
    final_line = f"{report.label}: {report.value}" if report.label else ""
    grades = [("final line", final_line_matches(case, report), f"final line '{final_line}'")]
    if expected.get("forbid_process_narration"):
        narration = review_report.contains_process_narration(response)
        grades.append(("process narration", not narration, "report holds no process narration"))
    if report.payload is not None:
        failures = class_failures(report.payload.get("findings", []), set(expected["expected_classes"]))
        grades.append(("classes", not failures, "; ".join(failures) or "classes match"))
    return grades

"""generay grading beyond the engine core, loaded by engine/run_eval.py.

The checks match the standalone generay eval runner at revision 309d425:
- expected.json carries expected_checks, expected_prescan, expect_json, and
  a non-empty notes string. Every listed check exists in TIME.md or SYNC.md.
  Optional fields keep their types.
- A PR case holds diff.patch and expects no prescan. Other cases hold an
  input.<ext> file or a named configuration file, and the scanners must
  report exactly the check IDs in expected_prescan.
- The model input is the generay envelope. Non-PR cases carry prescan
  candidates from the deterministic checks.
- Grading adds the expected check IDs from findings and escalations.
"""

from __future__ import annotations

import sys
from pathlib import Path

PERSONA_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PERSONA_DIR / "scripts"))

import check_doc_policy  # resolved through the path set above
import time_checks  # resolved through the path set above
import time_envelope  # resolved through the path set above
import time_report  # resolved through the path set above

REVIEW_MODE = "time"
POLICY_NAMES = ("TIME.md", "SYNC.md")
KNOWN_CHECKS = frozenset(
    check_id for name in POLICY_NAMES
    for check_id in check_doc_policy.parse_checks((PERSONA_DIR / name).read_text(encoding="ascii"))
)
RESERVED_FILES = frozenset({"expected.json", "context.md"})
CHECK_LIST_KEYS = ("expected_checks", "expected_prescan")


def _optional_field_problems(expected: dict) -> list[str]:
    """Return problems in the optional expected.json fields."""
    problems = []
    elapsed = expected.get("active_work_elapsed_seconds")
    if elapsed is not None and (isinstance(elapsed, bool) or not isinstance(elapsed, int) or elapsed < 0):
        problems.append("active_work_elapsed_seconds must be a non-negative integer")
    review_status = expected.get("expected_review_status")
    if review_status is not None and review_status != "NEEDS-HUMAN":
        problems.append("expected_review_status must be NEEDS-HUMAN")
    return problems


def validate_expected(mode: str, expected: dict) -> list[str]:
    """Return generay structure problems for one expected.json."""
    problems = [f"missing key '{key}'" for key in (*CHECK_LIST_KEYS, "expect_json") if key not in expected]
    if problems:
        return problems
    for key in CHECK_LIST_KEYS:
        if not isinstance(expected[key], list):
            problems.append(f"{key} must be a list")
            continue
        problems += [f"unknown check '{item}' in {key}" for item in expected[key] if item not in KNOWN_CHECKS]
    if mode == REVIEW_MODE and expected["expected_prescan"]:
        problems.append("PR cases carry no head tree, so expected_prescan must be empty")
    if not isinstance(expected["expect_json"], bool):
        problems.append("expect_json must be a boolean")
    if not isinstance(expected.get("notes"), str) or not expected["notes"].strip():
        problems.append("notes must be a non-empty string")
    return problems + _optional_field_problems(expected)


def case_files(case: dict) -> dict[str, str]:
    """Return the review files of one case keyed by file name."""
    case_dir = Path(case["dir"])
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(case_dir.iterdir())
            if path.is_file() and path.name not in RESERVED_FILES}


def scanned_names(case: dict) -> list[str]:
    """Return fixture names the scanners read: input.<ext> files and named configuration files."""
    return [name for name in case["files"]
            if name.startswith("input.") or name in time_checks.common.CONFIG_NAMES]


def prescan_for(case: dict) -> list[dict]:
    """Return checker candidates for non-PR input files. PR cases carry no head tree."""
    if case["mode"] == REVIEW_MODE:
        return []
    case_dir = Path(case["dir"])
    inputs = [case_dir / name for name in scanned_names(case)]
    findings = time_checks.run_checks(list(time_checks.CHECKS), inputs, case_dir)
    return time_checks.prescan_entries(findings, time_checks.load_methods())


def validate_case(case: dict) -> list[str]:
    """Return the generay fixture and prescan problems for one case."""
    if case["mode"] == REVIEW_MODE:
        return [] if "diff.patch" in case["files"] else ["PR mode requires diff.patch"]
    if not scanned_names(case):
        return ["non-PR mode requires an input.<ext> file or a named config file"]
    found = {item["check"] for item in prescan_for(case)}
    expected = set(case["expected"].get("expected_prescan", []))
    problems = [f"scanner missed expected check {item}" for item in sorted(expected - found)]
    return problems + [f"scanner reported unexpected check {item}" for item in sorted(found - expected)]


def build_model_input(case: dict, system_prompt: str) -> str:
    """Return the generay review envelope for one case."""
    del system_prompt
    metadata: dict[str, str | int] = {"source": "eval", "case": case["name"]}
    elapsed = case["expected"].get("active_work_elapsed_seconds")
    if elapsed is not None:
        metadata["active_work_elapsed_seconds"] = elapsed
    return time_envelope.build_envelope(case["prompt_mode"], case_files(case), case["context"],
                                        prescan_for(case), metadata)


def grade_response(case: dict, response: str) -> list[tuple[str, bool, str]]:
    """Return the expected-check grade beyond the engine core."""
    report = time_report.parse_report(response)
    if report.payload is None:
        return []
    entries = [*report.payload.get("findings", []), *report.payload.get("escalations", [])]
    reported = {item.get("check") for item in entries if isinstance(item, dict)}
    missing = [item for item in case["expected"]["expected_checks"] if item not in reported]
    detail = "missing " + ", ".join(missing) if missing else "expected checks reported"
    return [("checks", not missing, detail)]

"""foucault grading beyond the engine core, loaded by engine/run_eval.py.

The checks match the standalone foucault eval runner at revision 9ec9681:
- expected_review_status accepts only NEEDS-HUMAN.
- report_contract pins prior finding status and one required finding.
- omit_provenance sends the review target without the labeled envelope.
- VERDICT_JSON carries exactly mode, verdict, and findings.
"""

from __future__ import annotations

import json
import re

import check_review_response

REVIEW_MODE = "security"
VALID_JSON_MODES = frozenset({"PR", "File", "Piece", "Wholesale"})
VERDICT_JSON_KEYS = frozenset({"mode", "verdict", "findings"})
REPORT_CONTRACT_KEYS = frozenset({"forbid_process_narration", "require_prior_finding_status", "required_finding"})
REQUIRED_FINDING_KEYS = frozenset({"class", "file", "line"})
# A re-review report states the status of each earlier finding.
PRIOR_FINDING_STATUS_PATTERN = re.compile(
    r"\b(?:prior|previous|earlier)\b[^\n]{0,120}\b(?:resolved|still open|remains open)\b",
    re.IGNORECASE,
)


def _is_line_number(value: object) -> bool:
    """Return whether a value is a positive integer line number."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _required_finding_findings(finding: object, classes: object) -> list[str]:
    """Return findings for the required_finding of one report contract."""
    if not isinstance(finding, dict) or set(finding) != REQUIRED_FINDING_KEYS:
        return ["required_finding has an invalid shape"]
    findings = []
    if not isinstance(classes, list) or finding["class"] not in classes:
        findings.append("required_finding class must appear in expected_classes")
    if not isinstance(finding["file"], str) or not finding["file"]:
        findings.append("required_finding file is invalid")
    if not _is_line_number(finding["line"]):
        findings.append("required_finding line is invalid")
    return findings


def _report_contract_findings(mode: str, expected: dict) -> list[str]:
    """Return findings for an optional report_contract block."""
    contract = expected["report_contract"]
    if mode != REVIEW_MODE or expected.get("expect_json") is not True:
        return ["report_contract requires a JSON-enabled security case"]
    if not isinstance(contract, dict) or set(contract) != REPORT_CONTRACT_KEYS:
        return ["report_contract has an invalid shape"]
    findings = []
    if contract["forbid_process_narration"] is not True:
        findings.append("report_contract must forbid process narration")
    if contract["require_prior_finding_status"] is not True:
        findings.append("report_contract must require prior finding status")
    return findings + _required_finding_findings(contract["required_finding"], expected.get("expected_classes"))


def validate_expected(mode: str, expected: dict) -> list[str]:
    """Return foucault structure findings for one expected.json."""
    findings = []
    if expected.get("expected_review_status", "NEEDS-HUMAN") != "NEEDS-HUMAN":
        findings.append("expected_review_status must be NEEDS-HUMAN")
    if "report_contract" in expected:
        findings += _report_contract_findings(mode, expected)
    return findings


def build_model_input(case: dict, system_prompt: str) -> str | None:
    """Return the bare target for omit_provenance cases, else None for the default."""
    del system_prompt
    if not case["expected"].get("omit_provenance"):
        return None
    target = case["context"] + "\n\n" + case["case_text"]
    return json.dumps({"mode": case["prompt_mode"], "text": target}, ensure_ascii=True, sort_keys=True)


def _json_shape_grade(response: str) -> tuple[str, bool, str]:
    """Grade the exact key set and mode of the last VERDICT_JSON line."""
    lines = [line for line in response.splitlines() if line.startswith(check_review_response.VERDICT_JSON_PREFIX)]
    try:
        payload = json.loads(lines[-1][len(check_review_response.VERDICT_JSON_PREFIX) :].lstrip()) if lines else None
    except ValueError:
        payload = None
    passed = isinstance(payload, dict) and set(payload) == VERDICT_JSON_KEYS and payload["mode"] in VALID_JSON_MODES
    return "VERDICT_JSON shape", passed, "keys mode, verdict, findings with a foucault mode"


def _report_contract_grade(expected: dict, response: str) -> tuple[str, bool, str]:
    """Grade narration, prior finding status, and the required finding."""
    try:
        _verdict, payload = check_review_response.validate_response(response)
    except (check_review_response.ResponseError, UnicodeError) as error:
        return "report contract", False, f"invalid PR report: {error}"
    required = expected["report_contract"]["required_finding"]
    failures = []
    if not PRIOR_FINDING_STATUS_PATTERN.search(response):
        failures.append("prior finding status is absent")
    if not any(
        all(finding.get(key) == required[key] for key in REQUIRED_FINDING_KEYS) for finding in payload["findings"]
    ):
        failures.append("required finding evidence is absent")
    return "report contract", not failures, "; ".join(failures) or "report contract passed"


def grade_response(case: dict, response: str) -> list[tuple[str, bool, str]]:
    """Return foucault grades beyond the engine core."""
    expected = case["expected"]
    grades = []
    if expected.get("expect_json"):
        grades.append(_json_shape_grade(response))
    if expected.get("report_contract"):
        grades.append(_report_contract_grade(expected, response))
    return grades

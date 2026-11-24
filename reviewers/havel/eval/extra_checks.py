"""havel grading beyond the engine core, loaded by engine/run_eval.py.

The checks match the standalone havel eval runner at revision 5857143:
- A case holds at least one input file the havel runner reads.
- notes and fixture_notes are non-empty strings. Every fixture is synthetic.
- declared_scope, expected_regimes, and expected_regime_source agree with
  docs/regimes/scope-profiles.md.
- A 2.N@slug token in expected_classes names a known class and slug.
- A live reply carries the not-legal-advice line directly above its final
  verdict line.
- VERDICT_JSON names every expected class and the expected scope.

The engine core grades the verdict line and parses the VERDICT_JSON line.
build_model_input places declared_scope in TRUSTED_CONTEXT.options.regimes,
the field the CI envelope uses.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

PERSONA_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PERSONA_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import legal_notice  # resolved through the path set above
from run_eval import default_model_input, json_companion  # the engine directory joins the path first

CLASS_HEADING = re.compile(r"^\| \*\*(2\.\d+)\*\*", re.MULTILINE)
KNOWN_CLASSES = frozenset(CLASS_HEADING.findall((PERSONA_DIR / "AUDIT.md").read_text(encoding="utf-8")))
DELTA_TOKEN = re.compile(r"^(2\.\d+)@([a-z0-9-]+)$")
UNDECLARED = "undeclared"
VALID_REGIME_SOURCES = frozenset({"declared", "elicited", "undeclared"})
MANIFEST = json.loads((PERSONA_DIR / "reviewer.json").read_text(encoding="utf-8"))
# The input names the havel runner reads.
CASE_INPUT_NAMES = frozenset({
    "diff.patch",
    "input.py",
    "input.ts",
    "input.tsx",
    "input.js",
    "input.sql",
    "input.json",
    "input.yaml",
    "input.tf",
    "input.html",
    "input.md",
    "input.txt",
    "input.sh",
    "datamap.md",
    "ropa.json",
    "notice.md",
})


def _load_checker():
    """Return scripts/check_regime_refs.py and the profile table it reads."""
    spec = importlib.util.spec_from_file_location("havel_check_regime_refs", SCRIPTS_DIR / "check_regime_refs.py")
    if spec is None or spec.loader is None:
        raise ImportError("scripts/check_regime_refs.py cannot load. Restore the persona script.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.load_profiles(PERSONA_DIR)


CHECKER, PROFILES = _load_checker()


def _class_problems(classes: object) -> list[str]:
    """Return problems with the expected_classes tokens."""
    if not isinstance(classes, list):
        return ["expected_classes must be a list"]
    problems = []
    for token in classes:
        if not isinstance(token, str):
            problems.append(f"expected_classes entries must be strings: {token!r}")
            continue
        number, _, slug = token.partition("@")
        if number not in KNOWN_CLASSES:
            problems.append(f"unknown class '{number}' in expected_classes")
        if slug and (DELTA_TOKEN.match(token) is None or slug not in PROFILES["slugs"]):
            problems.append(f"expected_classes token '{token}' needs the form 2.N@slug with a known slug")
    return problems


def _asserted_regime_problems(asserted: object) -> list[str]:
    """Return problems with the expected_regimes list."""
    if asserted is None:
        return []
    if not isinstance(asserted, list) or not all(isinstance(slug, str) for slug in asserted):
        return ["expected_regimes must be a list of slugs"]
    unknown = sorted(set(asserted) - PROFILES["slugs"])
    return [f"expected_regimes names unknown {', '.join(unknown)}"] if unknown else []


def _scope_problems(expected: dict) -> list[str]:
    """Return problems where the declared scope and the asserted regimes disagree."""
    problems = []
    source = expected.get("expected_regime_source")
    if source is not None and source not in VALID_REGIME_SOURCES:
        problems.append(f"expected_regime_source '{source}' is not one of {sorted(VALID_REGIME_SOURCES)}")
    asserted = expected.get("expected_regimes")
    problems += _asserted_regime_problems(asserted)
    declared = expected.get("declared_scope")
    if declared is None or problems:
        return problems
    if not isinstance(declared, str):
        return ["declared_scope must be a string"]
    try:
        reachable = CHECKER.expand_scope(declared, PROFILES)
    except CHECKER.ScopeError as error:
        return [str(error)]
    if declared == UNDECLARED and asserted:
        problems.append("declared_scope is undeclared and expected_regimes is non-empty")
    elif asserted is not None and not set(asserted) <= reachable:
        beyond = ", ".join(sorted(set(asserted) - reachable))
        problems.append(f"expected_regimes names {beyond} beyond the reach of declared_scope '{declared}'")
    return problems


def _is_text(value: object) -> bool:
    """Return whether a value is a non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def validate_expected(mode: str, expected: dict) -> list[str]:
    """Return havel structure problems for one expected.json."""
    del mode
    if "expected_classes" not in expected:
        return ["missing key 'expected_classes'"]
    problems = _class_problems(expected["expected_classes"])
    if not _is_text(expected.get("notes")):
        problems.append("notes must be a non-empty string")
    # Every fixture states that its personal data is synthetic.
    if not _is_text(expected.get("fixture_notes")):
        problems.append("fixture_notes must state that the fixture data is synthetic")
    return problems + _scope_problems(expected)


def validate_case(case: dict) -> list[str]:
    """Return a problem when the case holds no input the havel runner reads."""
    if any(name in CASE_INPUT_NAMES for name in case["files"]):
        return []
    return ["no recognized input file present: " + ", ".join(case["files"])]


def build_model_input(case: dict, system_prompt: str) -> str:
    """Return the engine eval envelope with the declared scope in TRUSTED_CONTEXT.

    A case without declared_scope tests the ask branch and carries no
    TRUSTED_CONTEXT, as in the source runner.
    """
    envelope = json.loads(default_model_input(case, system_prompt))
    declared = case["expected"].get("declared_scope")
    if declared is not None:
        envelope["TRUSTED_CONTEXT"] = {"options": {"regimes": declared}}
    return json.dumps(envelope, ensure_ascii=True, sort_keys=True)


def _reported(payload: dict) -> list[tuple[str, set[str]]] | None:
    """Return (class, regime set) pairs from the companion, or None when malformed."""
    reported = []
    for finding in payload["findings"]:
        if not isinstance(finding, dict) or not isinstance(finding.get("class"), str):
            return None
        regime = finding.get("regime", [])
        regimes = regime if isinstance(regime, list) else [regime]
        reported.append((finding["class"], {str(slug) for slug in regimes}))
    return reported


def _token_reported(token: str, reported: list[tuple[str, set[str]]]) -> bool:
    """Return whether a 2.N or 2.N@slug token appears among the findings."""
    number, _, slug = token.partition("@")
    return any(found == number and (not slug or slug in regimes) for found, regimes in reported)


def _scope_detail(expected: dict, payload: dict) -> str:
    """Return why the companion scope differs from the case, or an empty string."""
    if "expected_regimes" in expected:
        regimes = payload.get("regimes")
        if not isinstance(regimes, list):
            return "VERDICT_JSON regimes is not a list"
        actual = sorted(str(slug) for slug in regimes)
        wanted = sorted(expected["expected_regimes"])
        if actual != wanted:
            return f"VERDICT_JSON regimes {actual} differ from expected {wanted}"
    source = expected.get("expected_regime_source")
    if source is not None and payload.get("regime_source") != source:
        return f"VERDICT_JSON regime_source '{payload.get('regime_source')}' differs from expected '{source}'"
    return ""


def _json_grade(expected: dict, response: str) -> tuple[str, bool, str]:
    """Grade the companion classes and scope against the case."""
    payload, detail = json_companion(response)
    if payload is None:
        return ("havel classes and scope", False, detail)
    reported = _reported(payload)
    if reported is None:
        return ("havel classes and scope", False, "VERDICT_JSON carries a finding without a string class")
    missing = [token for token in expected.get("expected_classes", []) if not _token_reported(token, reported)]
    if missing:
        return ("havel classes and scope", False, f"VERDICT_JSON omits expected class(es) {', '.join(missing)}")
    scope_detail = _scope_detail(expected, payload)
    return ("havel classes and scope", not scope_detail, scope_detail or "classes and scope match")


def grade_response(case: dict, response: str) -> list[tuple[str, bool, str]]:
    """Return the disclaimer grade and, where the case expects JSON, the scope grade."""
    label = MANIFEST["modes"][case["mode"]].get("verdict_line", "VERDICT")
    problem = legal_notice.disclaimer_problem(response, label)
    grades = [("not-legal-advice line", not problem, problem or "present above the verdict line")]
    if case["expected"].get("expect_json"):
        grades.append(_json_grade(case["expected"], response))
    return grades

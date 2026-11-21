#!/usr/bin/env python3
"""Check and grade the eval cases of one persona, review and local modes alike.

Cases live in reviewers/<persona>/eval/cases/<mode>/<case>/. Each case holds
an expected.json and at least one input file. Without --model-call the run
checks case structure only and calls no model. With --model-call the run
sends each case to a local callable and grades the reply.

A persona can ship reviewers/<persona>/eval/extra_checks.py. The engine
calls these optional functions from it:

- validate_expected(mode, expected) -> list[str]: extra structure findings
- validate_case(case) -> list[str]: extra findings on a loaded case, for
  example a required input file name
- build_model_input(case, system_prompt) -> str | None: the text the model
  receives, or None for the engine default
- grade_response(case, response) -> list[tuple[str, bool, str]]: extra grades
  as (label, passed, detail)

Usage:
    python engine/run_eval.py --persona foucault
    python engine/run_eval.py --persona foucault --mode file
    python engine/run_eval.py --persona foucault --model-call mymodule:call_model
    python engine/run_eval.py --persona foucault --model-call mymodule:call_model --repeat 5

--repeat N sends every case N times and reports, for each case, the share
of runs that return its most common verdict. Identical runs that disagree
mark a case with an unstable model verdict.

--extension-root names a repository root that supplies eval/extra_checks.py
in place of --root. The eval-live workflow grades pull request persona data
with the grader from the default branch, so no pull request Python runs.

--max-cases N fails the run before any model call when the selected cases
exceed N. Each case costs one model call per repeat.

A --model-call target is a callable call(system_prompt, mode, case_text) -> str.
The mode argument carries the json_mode of the mode, or the mode name.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

try:
    import persona_hooks
    import reviewers
except ImportError:
    from engine import persona_hooks, reviewers

ENGINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = ENGINE_DIR.parent

EXPECTED_NAME = "expected.json"
CONTEXT_NAME = "context.md"
HOOK_CONTEXT_NAME = "hook_context.md"
# Files in a case directory that carry no review target.
NON_INPUT_NAMES = frozenset({EXPECTED_NAME, CONTEXT_NAME, HOOK_CONTEXT_NAME, "README.md"})
REQUIRED_EXPECTED_KEYS = ("expected_verdict", "notes")
EXTENSION_PATH = Path("eval") / "extra_checks.py"
VERDICT_JSON_PREFIX = "VERDICT_JSON:"
REVIEW_STATUS_PREFIX = "REVIEW STATUS:"
REASON_SEPARATOR = " - "
# Each repeat costs one model call per case. The bound keeps a typo from
# starting thousands of calls.
MAX_REPEAT = 20
MISSING_VERDICT = "(no verdict line)"
ModelCall = Callable[[str, str, str], str]


class EvalError(ValueError):
    """A persona, case, or option the eval run refuses."""


def cases_root(persona_dir: Path, mode: str) -> Path:
    """Return the case directory of one mode."""
    return Path(persona_dir) / "eval" / "cases" / mode


def prompt_mode(mode_name: str, mode: dict) -> str:
    """Return the mode string the persona prompt expects."""
    return mode.get("json_mode", mode_name)


def accepted_verdict_forms(mode: dict) -> set[str]:
    """Return every expected_verdict spelling a case of this mode may use.

    Fixtures store a bare verdict ("HIGH"), the prefixed form ("RISK: HIGH"),
    the label alone ("RISK (partial)"), or the label with its colon ("RISK:").
    The last two assert the verdict line without pinning a value.
    """
    label, verdicts = reviewers.verdict_rules(mode)
    forms = {label, f"{label}:"}
    for verdict in verdicts:
        forms.update({verdict, f"{label}: {verdict}"})
    return forms


def load_extension(persona_dir: Path):
    """Return the persona extension module, or None when the persona ships none.

    An extension imports engine modules such as check_review_response by
    name, so the engine directory joins the import path first.
    """
    if str(ENGINE_DIR) not in sys.path:
        sys.path.insert(0, str(ENGINE_DIR))
    try:
        return persona_hooks.load_module(Path(persona_dir) / EXTENSION_PATH,
                                         f"extra_checks_{Path(persona_dir).name}")
    except ValueError as error:
        raise EvalError(f"{EXTENSION_PATH} must be a regular file") from error


def _read_text(path: Path) -> str:
    """Return a case file as text, or an empty string when it is absent."""
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _expected_findings(label: str, expected: object, mode_name: str, mode: dict) -> list[str]:
    """Return the shared structure findings of one expected.json."""
    if not isinstance(expected, dict):
        return [f"{label}: {EXPECTED_NAME} must hold a JSON object"]
    findings = [f"{label}: {EXPECTED_NAME} lacks '{key}'"
                for key in REQUIRED_EXPECTED_KEYS if key not in expected]
    verdict = expected.get("expected_verdict")
    if "expected_verdict" in expected and verdict not in accepted_verdict_forms(mode):
        findings.append(f"{label}: expected_verdict '{verdict}' does not fit mode '{mode_name}'")
    if "mode" in expected and expected["mode"] != prompt_mode(mode_name, mode):
        findings.append(f"{label}: mode '{expected['mode']}' does not match '{prompt_mode(mode_name, mode)}'")
    classes = expected.get("expected_classes", [])
    if not isinstance(classes, list) or not all(isinstance(item, str) for item in classes):
        findings.append(f"{label}: expected_classes must be a list of strings")
    return findings


def load_case(case_dir: Path, mode_name: str, mode: dict, extension=None) -> tuple[dict | None, list[str]]:
    """Return one case and its structure findings."""
    label = f"{mode_name}/{case_dir.name}"
    try:
        expected = json.loads((case_dir / EXPECTED_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return None, [f"{label}: {EXPECTED_NAME} is not readable UTF-8 JSON ({error})"]
    findings = _expected_findings(label, expected, mode_name, mode)
    inputs = sorted(path for path in case_dir.iterdir()
                    if path.is_file() and path.name not in NON_INPUT_NAMES)
    if not inputs:
        findings.append(f"{label}: holds no input file")
    if extension is not None and hasattr(extension, "validate_expected") and isinstance(expected, dict):
        findings += [f"{label}: {item}" for item in extension.validate_expected(mode_name, expected)]
    if findings:
        return None, findings
    case = {
        "name": case_dir.name,
        "dir": str(case_dir),
        "mode": mode_name,
        "prompt_mode": prompt_mode(mode_name, mode),
        "expected": expected,
        "context": _read_text(case_dir / CONTEXT_NAME),
        "hook_context": _read_text(case_dir / HOOK_CONTEXT_NAME),
        "case_text": "\n\n".join(path.read_text(encoding="utf-8") for path in inputs),
        "files": [path.name for path in inputs],
    }
    if extension is not None and hasattr(extension, "validate_case"):
        case_findings = [f"{label}: {item}" for item in extension.validate_case(case)]
        if case_findings:
            return None, case_findings
    return case, []


def selected_modes(manifest: dict, requested: str | None) -> list[str]:
    """Return the requested mode, or every mode of the manifest."""
    if requested is None:
        return list(manifest["modes"])
    if requested not in manifest["modes"]:
        raise EvalError(f"unknown mode '{requested}' for persona '{manifest['persona']}'")
    return [requested]


def collect_cases(persona_dir: Path, manifest: dict, mode: str | None = None,
                  only: str | None = None, extension=None) -> tuple[list[dict], list[str]]:
    """Return every valid case and every structure finding of one persona."""
    cases, findings = [], []
    for mode_name in selected_modes(manifest, mode):
        root = cases_root(persona_dir, mode_name)
        if not root.is_dir():
            continue
        for case_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            if only is not None and case_dir.name != only:
                continue
            case, case_findings = load_case(case_dir, mode_name, manifest["modes"][mode_name], extension)
            findings += case_findings
            if case is not None:
                cases.append(case)
    if only is not None and not cases and not findings:
        raise EvalError(f"no case named '{only}'")
    return cases, findings


def sha256_text(text: str) -> str:
    """Return the SHA-256 digest of text with LF line endings."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def default_model_input(case: dict, system_prompt: str) -> str:
    """Return the labeled, read-only JSON input of one case."""
    target = case["context"] + "\n\n" + case["case_text"]
    envelope = {
        "mode": case["prompt_mode"],
        "TRUSTED_HOOK_CONTEXT": {"read_only": True, "sha256": sha256_text(case["hook_context"]),
                                 "text": case["hook_context"]},
        "REVIEW_TARGET": {"sha256": sha256_text(target), "text": target},
        "policy_sha256": sha256_text(system_prompt),
    }
    return json.dumps(envelope, ensure_ascii=True, sort_keys=True)


def verdict_matches(expected_verdict: str, response: str, mode: dict) -> tuple[bool, str]:
    """Grade the final verdict line of a reply against the expected verdict.

    A reply quotes the reviewed text, and that text is untrusted. The prompt
    puts the authoritative verdict last, so the last matching line decides.
    """
    label, _verdicts = reviewers.verdict_rules(mode)
    prefix = f"{label}:"
    lines = [line for line in response.splitlines() if line.startswith(prefix)]
    if not lines:
        return False, f"no '{prefix}' line found in response"
    actual = lines[-1].strip()
    # The reason after " - " never decides the grade. Otherwise an expected
    # BLOCK would match "VERDICT: APPROVE - no BLOCK conditions observed".
    verdict = actual[len(prefix):].split(REASON_SEPARATOR, 1)[0].strip()
    accepted = {verdict, f"{label}: {verdict}", label, prefix}
    return expected_verdict in accepted, actual


def final_verdict(response: str, mode: dict) -> str:
    """Return the verdict token on the last verdict line of a reply."""
    label, _verdicts = reviewers.verdict_rules(mode)
    prefix = f"{label}:"
    lines = [line for line in response.splitlines() if line.startswith(prefix)]
    if not lines:
        return MISSING_VERDICT
    return lines[-1].strip()[len(prefix):].split(REASON_SEPARATOR, 1)[0].strip()


def agreement_lines(verdicts_by_case: dict[str, list[str]]) -> list[str]:
    """Return one agreement line per case and a closing total."""
    lines = []
    unanimous = 0
    for name, verdicts in verdicts_by_case.items():
        verdict, count = Counter(verdicts).most_common(1)[0]
        unanimous += 1 if count == len(verdicts) else 0
        lines.append(f"  agreement {name}: {count}/{len(verdicts)} {verdict}")
    lines.append(f"{unanimous}/{len(verdicts_by_case)} case(s) agree on every run")
    return lines


def review_status_matches(expected_status: str, response: str) -> bool:
    """Return whether the final REVIEW STATUS line carries the expected status."""
    lines = [line for line in response.splitlines() if line.startswith(REVIEW_STATUS_PREFIX)]
    return bool(lines) and lines[-1].startswith(f"{REVIEW_STATUS_PREFIX} {expected_status}")


def json_companion(response: str) -> tuple[dict | None, str]:
    """Return the object on the last VERDICT_JSON line and a detail message."""
    lines = [line for line in response.splitlines() if line.startswith(VERDICT_JSON_PREFIX)]
    if not lines:
        return None, "no VERDICT_JSON: line found"
    try:
        payload = json.loads(lines[-1][len(VERDICT_JSON_PREFIX):].lstrip())
    except ValueError as error:
        return None, f"VERDICT_JSON did not parse: {error}"
    if not isinstance(payload, dict):
        return None, "VERDICT_JSON is not an object"
    if not isinstance(payload.get("verdict"), str) or not isinstance(payload.get("findings"), list):
        return None, "VERDICT_JSON needs a string verdict and a findings list"
    return payload, "VERDICT_JSON parsed"


def grade_response(case: dict, response: str, mode: dict, extension=None) -> list[tuple[str, bool, str]]:
    """Return every grade of one reply as (label, passed, detail)."""
    expected = case["expected"]
    passed, detail = verdict_matches(expected["expected_verdict"], response, mode)
    grades = [("verdict", passed, f"expected '{expected['expected_verdict']}', got '{detail}'")]
    if "expected_review_status" in expected:
        status_ok = review_status_matches(expected["expected_review_status"], response)
        grades.append(("REVIEW STATUS", status_ok, f"expected '{expected['expected_review_status']}'"))
    if expected.get("expect_json"):
        payload, json_detail = json_companion(response)
        grades.append(("VERDICT_JSON", payload is not None, json_detail))
    if extension is not None and hasattr(extension, "grade_response"):
        grades += list(extension.grade_response(case, response))
    return grades


def resolve_model_call(spec: str) -> ModelCall:
    """Return the callable a module:function spec names."""
    module_name, _, function_name = spec.partition(":")
    if not module_name or not function_name:
        raise EvalError("--model-call must use the form module:function")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    function = getattr(importlib.import_module(module_name), function_name, None)
    if not callable(function):
        raise EvalError(f"--model-call target '{spec}' is not callable")
    return function


def run_live(persona_dir: Path, manifest: dict, cases: list[dict], model_call: ModelCall,
             extension=None, repeat: int = 1) -> int:
    """Send every case to the model repeat times, print each grade, and return the failure count."""
    custom_input = getattr(extension, "build_model_input", None)
    failures = checks = 0
    verdicts_by_case: dict[str, list[str]] = {}
    for case in cases:
        mode = manifest["modes"][case["mode"]]
        name = f"{case['mode']}/{case['name']}"
        system_prompt = reviewers.prompt_path(persona_dir, mode["prompt"]).read_text(encoding="utf-8")
        model_input = custom_input(case, system_prompt) if custom_input else None
        if model_input is None:
            model_input = default_model_input(case, system_prompt)
        for _run in range(repeat):
            response = model_call(system_prompt, case["prompt_mode"], model_input)
            verdicts_by_case.setdefault(name, []).append(final_verdict(response, mode))
            for label, passed, detail in grade_response(case, response, mode, extension):
                checks += 1
                failures += 0 if passed else 1
                print(f"  {'pass' if passed else 'FAIL'}  {name} ({label}): {detail}")
    print(f"\n{checks - failures}/{checks} response checks passed")
    if repeat > 1 and verdicts_by_case:
        print("\n".join(agreement_lines(verdicts_by_case)))
    return failures


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--persona", required=True, help="persona directory name under reviewers/")
    parser.add_argument("--mode", help="run only this mode")
    parser.add_argument("--case", help="run only the named case")
    parser.add_argument("--model-call", help="module:function called as call(system_prompt, mode, case_text)")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root")
    parser.add_argument("--extension-root", type=Path,
                        help="repository root that supplies eval/extra_checks.py in place of --root")
    parser.add_argument("--max-cases", type=positive_count,
                        help="fail before any model call when the selected cases exceed this count")
    parser.add_argument("--repeat", type=repeat_count, default=1,
                        help=f"send every case this many times, 1 to {MAX_REPEAT}, and report verdict agreement")
    return parser.parse_args(argv)


def positive_count(value: str) -> int:
    """Return a positive integer, or raise an argparse error."""
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"expected a positive integer, not {value!r}") from error
    if count < 1:
        raise argparse.ArgumentTypeError(f"expected a positive integer, not {count}")
    return count


def repeat_count(value: str) -> int:
    """Return a repeat count within 1 to MAX_REPEAT, or raise an argparse error."""
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"--repeat takes an integer, not {value!r}") from error
    if not 1 <= count <= MAX_REPEAT:
        raise argparse.ArgumentTypeError(f"--repeat takes 1 to {MAX_REPEAT}, not {count}")
    return count


def main(argv: list[str]) -> int:
    """Check structure, then grade replies when --model-call names a callable."""
    options = parse_arguments(argv)
    try:
        persona_dir, manifest = reviewers.load_persona(options.root, options.persona)
        extension_root = options.extension_root
        extension_dir = extension_root / "reviewers" / persona_dir.name if extension_root else persona_dir
        extension = load_extension(extension_dir)
        cases, findings = collect_cases(persona_dir, manifest, options.mode, options.case, extension)
        model_call = resolve_model_call(options.model_call) if options.model_call else None
        if options.repeat > 1 and model_call is None:
            raise EvalError("--repeat needs --model-call")
        if options.max_cases is not None and len(cases) > options.max_cases:
            raise EvalError(f"{len(cases)} case(s) exceed --max-cases {options.max_cases}")
    except (reviewers.ReviewerError, EvalError, ImportError) as error:
        print(f"error: {error}. Fix the option or the persona files and rerun.", file=sys.stderr)
        return 1
    if findings:
        for finding in findings:
            print(f"error: {finding}", file=sys.stderr)
        print("Fix each case named above, then rerun.", file=sys.stderr)
        return 1
    if model_call is None:
        print(f"structure check only: {len(cases)} case(s) valid, no model call configured")
        return 0
    return 1 if run_live(persona_dir, manifest, cases, model_call, extension, options.repeat) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

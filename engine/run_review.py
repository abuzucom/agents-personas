#!/usr/bin/env python3
"""Review one pull request mode end to end and write result.json.

The runner builds the fenced envelopes, calls the model once per chunk, and
validates each reply. An invalid reply gets one retry with a validation note
in the system prompt. A second invalid reply fails the run, so the check
never reports a pass without a verdict. An adapter capacity exit records
NEEDS-HUMAN for that chunk.

A chunk BLOCK gets one confirmation run with the same prompt and envelope.
The BLOCK stands only when that run blocks again with a finding class from
the first run. Otherwise the chunk records NEEDS-HUMAN. A model can block
one run and approve the next on the same input, so a lone BLOCK never fails
a check without a person.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import build_pr_case
    import check_review_response
    import envelope
    import persona_hooks
    import review_output
    import sandbox
    import reviewers
except ImportError:
    from engine import (build_pr_case, check_review_response, envelope, persona_hooks, review_output, reviewers,
                        sandbox)

ENGINE_DIR = Path(__file__).resolve().parent
# call_model.py exits with this code when no configured model can hold the input.
CAPACITY_EXIT_CODE = 3
STAGES = ("all", "build", "review")
# Every persona hook runs in a child process with only these variables, plus
# LC_* locale variables. A credential never reaches persona code.
HOOK_ENVIRONMENT_NAMES = frozenset({"PATH", "HOME", "USERPROFILE", "LANG", "TMPDIR", "TEMP", "TMP",
                                    "SYSTEMROOT", "PATHEXT", "COMSPEC"})
HOOK_LOCALE_PREFIX = "LC_"
# These point at the hook child's own empty temporary directory.
HOOK_HOME_VARIABLES = ("HOME", "USERPROFILE", "TMPDIR", "TEMP", "TMP")
HOOK_TIMEOUT_SECONDS = 300
# Linux prctl option that controls /proc access and ptrace by same-user processes.
PR_SET_DUMPABLE = 4
# The provider adapter applies its own request timeout and retry. This bound
# stops a hung adapter process.
ADAPTER_TIMEOUT_SECONDS = 1800
MAX_PROBLEM_CHARS = 500
RETRY_NOTE = (
    "Engine note: the previous response failed validation ({problem}). Return a "
    "report that ends with the VERDICT line and the VERDICT_JSON line."
)


class ReviewError(RuntimeError):
    """A mode run that produced no valid verdict."""


@dataclass(frozen=True)
class RunOptions:
    """Inputs for one mode run."""

    root: Path
    persona: str
    mode: str
    repo: Path
    base: str
    head: str
    pr_number: int
    out_dir: Path
    title: str
    body: str
    requested_caps: dict = field(default_factory=dict)
    model_call_command: str = ""
    # "build" writes the case and calls no model. The workflow runs it in a
    # step without the provider key. "review" reads that case. "all" does both.
    stage: str = "all"
    persona_options: str = ""


@dataclass
class ChunkResult:
    """The outcome of one chunk review."""

    verdict: str
    findings: list
    report: str
    usage: dict
    reason: str = ""


def adapter_command(options: RunOptions) -> tuple[list[str], dict]:
    """Return the adapter argument array and its extra environment."""
    if options.model_call_command:
        command = [sys.executable, str(ENGINE_DIR / "run_model_command.py")]
        return command, {"MODEL_CALL_COMMAND": options.model_call_command}
    return [sys.executable, str(ENGINE_DIR / "call_model.py")], {}


def call_adapter(options: RunOptions, prompt_path: Path, case_path: Path,
                 usage_path: Path) -> subprocess.CompletedProcess:
    """Run the adapter once for one prompt and one envelope."""
    command, extra = adapter_command(options)
    environment = {**os.environ, **extra, "AUDIT_PROMPT_FILE": str(prompt_path),
                   "CASE_TEXT_FILE": str(case_path), "USAGE_FILE": str(usage_path)}
    try:
        return subprocess.run(command, cwd=options.repo, env=environment, capture_output=True,
                              text=True, encoding="utf-8", timeout=ADAPTER_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as error:
        raise ReviewError(f"model command timed out after {ADAPTER_TIMEOUT_SECONDS} s") from error


def read_usage(usage_path: Path) -> dict:
    """Return the token counts the adapter wrote, or empty counts."""
    try:
        usage = json.loads(usage_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return usage if isinstance(usage, dict) else {}


def hook_environment() -> dict[str, str]:
    """Return the allowlisted environment for a persona hook child process."""
    return {key: value for key, value in os.environ.items()
            if key.upper() in HOOK_ENVIRONMENT_NAMES or key.upper().startswith(HOOK_LOCALE_PREFIX)}


def call_hook(persona_dir: Path | None, name: str, arguments: list,
              writable: list[Path] | None = None) -> tuple[bool, object]:
    """Run one persona hook in a child process with the allowlisted environment.

    Return whether the persona defines the hook and its JSON result. The
    parent process never imports the persona hook file.
    """
    if persona_dir is None or not (Path(persona_dir) / persona_hooks.REVIEW_HOOKS_NAME).exists():
        return False, None
    command = [sandbox.interpreter(), str((ENGINE_DIR / "run_hook.py").resolve()), "--persona-dir",
               str(Path(persona_dir).resolve()), "--hook", name]
    # The child starts in a fresh empty directory. That directory is also its
    # home and temp directory. On Linux bubblewrap removes the network and every
    # runner path except the engine, the persona, and the writable paths.
    with tempfile.TemporaryDirectory(prefix="persona-hook-") as workdir:
        environment = {**hook_environment(), **dict.fromkeys(HOOK_HOME_VARIABLES, workdir)}
        try:
            command = sandbox.wrap(command, Path(workdir), [ENGINE_DIR, Path(persona_dir)], list(writable or []))
        except sandbox.SandboxUnavailable as error:
            raise ReviewError(str(error)) from error
        try:
            completed = subprocess.run(command, input=json.dumps(arguments), env=environment, cwd=workdir,
                                       capture_output=True, text=True, encoding="utf-8",
                                       timeout=HOOK_TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired as error:
            raise ReviewError(f"persona hook {name} timed out after {HOOK_TIMEOUT_SECONDS} s") from error
    if completed.returncode:
        diagnostics = review_output.clean_text(completed.stderr.strip(), MAX_PROBLEM_CHARS)
        raise ReviewError(f"persona hook {name} failed: {diagnostics}")
    output = json.loads(completed.stdout)
    if output.get("absent"):
        return False, None
    return True, output["result"]


def validate_reply(response: str, case_path: Path, json_mode: str | None, finding_rules: dict | None,
                   persona_dir: Path | None = None) -> tuple[str, dict]:
    """Return the verdict and payload of a reply that passes the engine and persona checks."""
    verdict, payload = check_review_response.validate_response(response, json_mode, finding_rules)
    sent = json.loads(case_path.read_text(encoding="utf-8"))
    present, problems = call_hook(persona_dir, "validate_reply", [payload, response, sent])
    if present and not isinstance(problems, list):
        raise ReviewError("persona hook validate_reply returned no list")
    if present and problems:
        raise check_review_response.ResponseError("; ".join(str(item) for item in problems))
    return verdict, payload


def review_chunk(options: RunOptions, system_prompt: str, case_path: Path,
                 json_mode: str | None, finding_rules: dict | None = None,
                 persona_dir: Path | None = None, run_name: str = "") -> ChunkResult:
    """Review one envelope with at most one retry after an invalid reply."""
    work = case_path.parent
    stem = f"{case_path.stem}.{run_name}" if run_name else case_path.stem
    note = ""
    problem = ""
    for attempt in range(2):
        prompt_path = work / f"{stem}.prompt.{attempt}.txt"
        usage_path = work / f"{stem}.usage.{attempt}.json"
        prompt_path.write_text(system_prompt + note, encoding="utf-8", newline="\n")
        completed = call_adapter(options, prompt_path, case_path, usage_path)
        if completed.returncode == CAPACITY_EXIT_CODE:
            return ChunkResult("NEEDS-HUMAN", [], "", {}, "input exceeds every model capacity")
        if completed.returncode:
            diagnostics = review_output.clean_text(completed.stderr.strip(), MAX_PROBLEM_CHARS)
            raise ReviewError(f"model command failed with exit code {completed.returncode}: {diagnostics}")
        try:
            verdict, payload = validate_reply(completed.stdout, case_path, json_mode, finding_rules, persona_dir)
        except check_review_response.ResponseError as error:
            problem = str(error)[:MAX_PROBLEM_CHARS]
            note = "\n\n" + RETRY_NOTE.format(problem=problem) + "\n"
            continue
        return ChunkResult(verdict, payload["findings"], completed.stdout, read_usage(usage_path))
    raise ReviewError(f"invalid response after one retry: {problem}")


def finding_classes(findings: list) -> set:
    """Return the class of each finding, or its file when the persona declares no class."""
    return {str(item.get("class") or item.get("file")) for item in findings if isinstance(item, dict)}


def confirm_block(first: ChunkResult, confirmation: ChunkResult) -> ChunkResult:
    """Return the first BLOCK when the confirmation repeats a class, else NEEDS-HUMAN."""
    usage = sum_usage([first, confirmation])
    repeated = finding_classes(first.findings) & finding_classes(confirmation.findings)
    if confirmation.verdict == "BLOCK" and repeated:
        return ChunkResult("BLOCK", first.findings, first.report, usage, first.reason)
    reason = (f"BLOCK not confirmed: the confirmation run returned {confirmation.verdict} "
              "without a repeated finding class")
    return ChunkResult("NEEDS-HUMAN", first.findings, first.report, usage, reason)


def review_confirmed_chunk(options: RunOptions, system_prompt: str, case_path: Path, entry: dict,
                           persona_dir: Path | None) -> ChunkResult:
    """Review one envelope and confirm a BLOCK with one more run."""
    arguments = (options, system_prompt, case_path, entry.get("json_mode"), entry.get("finding_rules"), persona_dir)
    first = review_chunk(*arguments)
    if first.verdict != "BLOCK":
        return first
    return confirm_block(first, review_chunk(*arguments, run_name="confirm"))


def sum_usage(results: list[ChunkResult]) -> dict:
    """Return summed token counts, or None where no chunk reported one."""
    totals = {}
    for key in ("input_tokens", "output_tokens"):
        values = [item.usage.get(key) for item in results if isinstance(item.usage.get(key), int)]
        totals[key] = sum(values) if values else None
    return totals


class ChildHooks:
    """Expose case_context to the case builder through a child process."""

    def __init__(self, persona_dir: Path):
        self.persona_dir = Path(persona_dir)

    def case_context(self, head_dir: Path, changed: list[str], patches: dict, options: dict) -> dict:
        """Return the persona context, or an empty result when the persona defines none."""
        present, result = call_hook(self.persona_dir, "case_context", [str(head_dir), changed, patches, options],
                                    writable=[Path(head_dir)])
        return result if present else {"context": {}, "unreviewed": []}


def build_case(options: RunOptions, caps: dict, hooks=None, persona_options: dict | None = None) -> dict:
    """Build the envelopes and return the case manifest."""
    case_dir = options.out_dir / "case"
    build_pr_case.build(build_pr_case.BuildOptions(
        repo=options.repo, base=options.base, head=options.head, out_dir=case_dir,
        persona=options.persona, mode=options.mode, title=options.title, body=options.body,
        pr_number=options.pr_number, max_chunks=caps["max_chunks"],
        max_envelope_bytes=caps["max_envelope_bytes"], hooks=hooks,
        persona_options=persona_options or {},
    ))
    return json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))


def read_built_case(options: RunOptions, caps: dict, persona_options: dict) -> dict:
    """Return the manifest the build stage wrote for exactly these review inputs."""
    manifest_path = options.out_dir / "case" / "manifest.json"
    if not manifest_path.is_file():
        raise ReviewError(f"no built case at {manifest_path}. run the build stage first")
    case = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "persona": options.persona, "mode": options.mode, "base_sha": options.base, "head_sha": options.head,
        "pr_number": options.pr_number, "max_chunks": caps["max_chunks"],
        "max_envelope_bytes": caps["max_envelope_bytes"],
        "persona_options_sha256": build_pr_case.options_digest(persona_options),
    }
    differing = sorted(key for key, value in expected.items() if case.get(key) != value)
    if differing:
        raise ReviewError(f"the built case differs in {', '.join(differing)}. Rerun the build stage")
    return case


def apply_forced_verdict(verdict: str, reasons: list[str], options: RunOptions,
                         persona_dir: Path | None = None) -> str:
    """Return the run verdict after a persona forced_verdict hook."""
    context_path = options.out_dir / "case" / build_pr_case.CASE_CONTEXT_NAME
    present, forced = call_hook(persona_dir, "forced_verdict",
                                       [json.loads(context_path.read_text(encoding="utf-8"))])
    if not present or not forced:
        return verdict
    forced_verdict, reason = forced
    if forced_verdict not in review_output.VERDICT_RANK:
        raise ReviewError(f"forced_verdict returned the unknown verdict {forced_verdict!r}")
    if review_output.VERDICT_RANK[forced_verdict] > review_output.VERDICT_RANK[verdict]:
        reasons.append(str(reason))
        return forced_verdict
    return verdict


def run_mode(options: RunOptions) -> dict:
    """Review one mode, write result.json, and return the result."""
    started = time.monotonic()
    persona_dir, manifest = reviewers.load_persona(options.root, options.persona)
    reviewers.resolve_review_modes(manifest, options.mode)
    entry = manifest["modes"][options.mode]
    if options.stage not in STAGES:
        raise ReviewError(f"unknown stage {options.stage!r}. Use one of {', '.join(STAGES)}")
    caps = reviewers.resolve_caps(entry, options.requested_caps)
    persona_options = reviewers.resolve_options(manifest, options.persona_options)
    if options.stage == "review":
        case = read_built_case(options, caps, persona_options)
    else:
        # The parent never imports the hook file. case_context runs in a child.
        case = build_case(options, caps, ChildHooks(persona_dir), persona_options)
    if options.stage == "build":
        return {"stage": "build", "chunks": len(case["chunks"]), "unreviewed": case["unreviewed"]}
    prompt_text = reviewers.prompt_path(persona_dir, entry["prompt"]).read_text(encoding="utf-8")
    system_prompt = envelope.with_fence_rule(prompt_text)
    case_dir = options.out_dir / "case" / "envelopes"
    results = [review_confirmed_chunk(options, system_prompt, case_dir / chunk["envelope"], entry, persona_dir)
               for chunk in case["chunks"]]
    verdict, reasons = review_output.combine_verdicts([item.verdict for item in results], case["unreviewed"])
    verdict = apply_forced_verdict(verdict, reasons, options, persona_dir)
    result = {
        "persona": options.persona, "mode": options.mode, "base_sha": options.base, "head_sha": options.head,
        "verdict": verdict, "reasons": reasons + [item.reason for item in results if item.reason],
        "chunk_results": [
            {"name": Path(chunk["envelope"]).stem, "verdict": item.verdict, "report": item.report,
             "reason": item.reason}
            for chunk, item in zip(case["chunks"], results, strict=True)
        ],
        "findings": [finding for item in results for finding in item.findings],
        "changed_files": case["changed_files"], "unreviewed": case["unreviewed"],
        "chunks": len(case["chunks"]), "clamped": caps["clamped"], "usage": sum_usage(results),
        "duration_seconds": round(time.monotonic() - started, 1),
        "reports": [item.report for item in results if item.report],
    }
    (options.out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n",
                                                encoding="utf-8", newline="\n")
    return result


def protect_environment() -> None:
    """Mark this process non-dumpable on Linux.

    A same-user process can read /proc/<pid>/environ of a dumpable process.
    This process holds MODEL_API_KEY. A non-dumpable process keeps its
    environ and memory from persona hook children and from ptrace.
    """
    if not sys.platform.startswith("linux"):
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        raise ReviewError(f"prctl(PR_SET_DUMPABLE) failed with errno {ctypes.get_errno()}")


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    """Return parsed command line options."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ENGINE_DIR.parent)
    parser.add_argument("--persona", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-chunks", type=int)
    parser.add_argument("--max-envelope-bytes", type=int)
    parser.add_argument("--stage", choices=STAGES, default="all",
                        help="build writes the case only. review reads a built case")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """Run one mode from the command line and the workflow environment."""
    protect_environment()
    args = parse_arguments(argv)
    requested = {name: value for name, value in (("max_chunks", args.max_chunks),
                                                 ("max_envelope_bytes", args.max_envelope_bytes))
                 if value is not None}
    options = RunOptions(
        root=args.root, persona=args.persona, mode=args.mode, repo=args.repo, base=args.base,
        head=args.head, pr_number=args.pr_number, out_dir=args.out_dir,
        title=os.environ.get("PR_TITLE", ""), body=os.environ.get("PR_BODY", ""),
        requested_caps=requested, model_call_command=os.environ.get("MODEL_CALL_COMMAND", ""),
        stage=args.stage, persona_options=os.environ.get("PERSONA_OPTIONS", ""),
    )
    try:
        result = run_mode(options)
    except (ReviewError, ValueError, RuntimeError, OSError) as error:
        print(f"error: {error}. The mode produced no verdict. Fix the cause and rerun.", file=sys.stderr)
        return 1
    if options.stage == "build":
        print(f"built {result['chunks']} chunk(s), {len(result['unreviewed'])} unreviewed file(s)")
        return 0
    print(f"VERDICT: {result['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

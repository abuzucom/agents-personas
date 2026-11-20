#!/usr/bin/env python3
"""Review one pull request mode end to end and write result.json.

The runner builds the fenced envelopes, calls the model once per chunk, and
validates each reply. An invalid reply gets one retry with a validation note
in the system prompt. A second invalid reply fails the run, so the check
never reports a pass without a verdict. An adapter capacity exit records
NEEDS-HUMAN for that chunk.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import build_pr_case
    import check_review_response
    import envelope
    import review_output
    import reviewers
except ImportError:
    from engine import build_pr_case, check_review_response, envelope, review_output, reviewers

ENGINE_DIR = Path(__file__).resolve().parent
# call_model.py exits with this code when no configured model can hold the input.
CAPACITY_EXIT_CODE = 3
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


def review_chunk(options: RunOptions, system_prompt: str, case_path: Path,
                 json_mode: str | None) -> ChunkResult:
    """Review one envelope with at most one retry after an invalid reply."""
    work = case_path.parent
    note = ""
    problem = ""
    for attempt in range(2):
        prompt_path = work / f"{case_path.stem}.prompt.{attempt}.txt"
        usage_path = work / f"{case_path.stem}.usage.{attempt}.json"
        prompt_path.write_text(system_prompt + note, encoding="utf-8", newline="\n")
        completed = call_adapter(options, prompt_path, case_path, usage_path)
        if completed.returncode == CAPACITY_EXIT_CODE:
            return ChunkResult("NEEDS-HUMAN", [], "", {}, "input exceeds every model capacity")
        if completed.returncode:
            diagnostics = review_output.clean_text(completed.stderr.strip(), MAX_PROBLEM_CHARS)
            raise ReviewError(f"model command failed with exit code {completed.returncode}: {diagnostics}")
        try:
            verdict, payload = check_review_response.validate_response(completed.stdout, json_mode)
        except check_review_response.ResponseError as error:
            problem = str(error)[:MAX_PROBLEM_CHARS]
            note = "\n\n" + RETRY_NOTE.format(problem=problem) + "\n"
            continue
        return ChunkResult(verdict, payload["findings"], completed.stdout, read_usage(usage_path))
    raise ReviewError(f"invalid response after one retry: {problem}")


def sum_usage(results: list[ChunkResult]) -> dict:
    """Return summed token counts, or None where no chunk reported one."""
    totals = {}
    for key in ("input_tokens", "output_tokens"):
        values = [item.usage.get(key) for item in results if isinstance(item.usage.get(key), int)]
        totals[key] = sum(values) if values else None
    return totals


def build_case(options: RunOptions, caps: dict) -> dict:
    """Build the envelopes and return the case manifest."""
    case_dir = options.out_dir / "case"
    build_pr_case.build(build_pr_case.BuildOptions(
        repo=options.repo, base=options.base, head=options.head, out_dir=case_dir,
        persona=options.persona, mode=options.mode, title=options.title, body=options.body,
        pr_number=options.pr_number, max_chunks=caps["max_chunks"],
        max_envelope_bytes=caps["max_envelope_bytes"],
    ))
    return json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))


def run_mode(options: RunOptions) -> dict:
    """Review one mode, write result.json, and return the result."""
    started = time.monotonic()
    persona_dir, manifest = reviewers.load_persona(options.root, options.persona)
    reviewers.resolve_review_modes(manifest, options.mode)
    entry = manifest["modes"][options.mode]
    caps = reviewers.resolve_caps(entry, options.requested_caps)
    case = build_case(options, caps)
    prompt_text = reviewers.prompt_path(persona_dir, entry["prompt"]).read_text(encoding="utf-8")
    system_prompt = envelope.with_fence_rule(prompt_text)
    case_dir = options.out_dir / "case" / "envelopes"
    results = [review_chunk(options, system_prompt, case_dir / chunk["envelope"], entry.get("json_mode"))
               for chunk in case["chunks"]]
    verdict, reasons = review_output.combine_verdicts([item.verdict for item in results], case["unreviewed"])
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
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """Run one mode from the command line and the workflow environment."""
    args = parse_arguments(argv)
    requested = {name: value for name, value in (("max_chunks", args.max_chunks),
                                                 ("max_envelope_bytes", args.max_envelope_bytes))
                 if value is not None}
    options = RunOptions(
        root=args.root, persona=args.persona, mode=args.mode, repo=args.repo, base=args.base,
        head=args.head, pr_number=args.pr_number, out_dir=args.out_dir,
        title=os.environ.get("PR_TITLE", ""), body=os.environ.get("PR_BODY", ""),
        requested_caps=requested, model_call_command=os.environ.get("MODEL_CALL_COMMAND", ""),
    )
    try:
        result = run_mode(options)
    except (ReviewError, ValueError, RuntimeError, OSError) as error:
        print(f"error: {error}. The mode produced no verdict. Fix the cause and rerun.", file=sys.stderr)
        return 1
    print(f"VERDICT: {result['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

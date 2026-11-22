#!/usr/bin/env python3
"""Run one persona hook in a child process with an allowlisted environment.

engine/run_review.py starts this script for case_context, validate_reply,
and forced_verdict in every stage. The child environment holds only the
allowlisted variables, so persona hook code never runs beside the provider
key or another credential. Standard input carries a JSON list of
arguments. Standard output carries {"absent": true} when the persona defines
no such hook, or {"result": <value>} otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The engine directory joins the import path, so these imports resolve
# both when a script runs directly and when a test loads it from a file.
_ENGINE_DIR = str(Path(__file__).resolve().parent)
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

import persona_hooks  # resolved through the path set above

HOOKS = ("case_context", "validate_reply", "forced_verdict")


def run_hook(persona_dir: Path, name: str, arguments: list) -> dict:
    """Return the hook result wrapped for the parent process."""
    hooks = persona_hooks.load_review_hooks(persona_dir)
    hook = getattr(hooks, name, None)
    if hook is None:
        return {"absent": True}
    if name == "case_context":
        # JSON carries the head tree directory as a string.
        arguments = [Path(arguments[0]), *arguments[1:]]
    return {"result": hook(*arguments)}


def main(argv: list[str]) -> int:
    """Read the arguments, call the hook, and print the wrapped result."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--persona-dir", type=Path, required=True)
    parser.add_argument("--hook", choices=HOOKS, required=True)
    options = parser.parse_args(argv)
    try:
        arguments = json.loads(sys.stdin.read())
        if not isinstance(arguments, list):
            raise ValueError("hook arguments must be a JSON list")
        output = run_hook(options.persona_dir, options.hook, arguments)
        sys.stdout.write(json.dumps(output))
    except (ValueError, OSError, TypeError) as error:
        print(f"error: hook {options.hook} failed: {error}. Fix the persona hook and rerun.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

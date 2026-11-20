#!/usr/bin/env python3
"""Run one review-stage persona hook in a child process without the provider key.

engine/run_review.py starts this script for validate_reply and forced_verdict.
The parent removes MODEL_API_KEY from the child environment, so persona hook
code never runs beside the key. Standard input carries a JSON list of
arguments. Standard output carries {"absent": true} when the persona defines
no such hook, or {"result": <value>} otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import persona_hooks
except ImportError:
    from engine import persona_hooks

REVIEW_STAGE_HOOKS = ("validate_reply", "forced_verdict")


def run_hook(persona_dir: Path, name: str, arguments: list) -> dict:
    """Return the hook result wrapped for the parent process."""
    hooks = persona_hooks.load_review_hooks(persona_dir)
    hook = getattr(hooks, name, None)
    if hook is None:
        return {"absent": True}
    return {"result": hook(*arguments)}


def main(argv: list[str]) -> int:
    """Read the arguments, call the hook, and print the wrapped result."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--persona-dir", type=Path, required=True)
    parser.add_argument("--hook", choices=REVIEW_STAGE_HOOKS, required=True)
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

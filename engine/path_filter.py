#!/usr/bin/env python3
"""Decide whether a pull request touches any file a persona caller selected.

The caller passes newline-separated glob patterns. "**" crosses directory
levels and "*" stays inside one. Empty patterns select every pull request.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path, PurePosixPath

MAX_PATTERNS = 100
MAX_PATTERN_CHARS = 256


def parse_patterns(text: str) -> list[str]:
    """Return validated patterns, one per non-blank, non-comment line."""
    patterns = [line.strip() for line in text.splitlines()]
    patterns = [line for line in patterns if line and not line.startswith("#")]
    if len(patterns) > MAX_PATTERNS:
        raise ValueError(f"paths holds at most {MAX_PATTERNS} patterns")
    for pattern in patterns:
        if not pattern.isascii() or not pattern.isprintable():
            raise ValueError(f"pattern {pattern!r} must be printable ASCII")
        if len(pattern) > MAX_PATTERN_CHARS:
            raise ValueError(f"pattern {pattern!r} exceeds {MAX_PATTERN_CHARS} characters")
        if pattern.startswith("/") or ".." in pattern.split("/"):
            raise ValueError(f"pattern {pattern!r} must be a relative repository path")
    return patterns


def any_match(files: list[str], patterns: list[str]) -> bool:
    """Return whether any changed file matches any pattern."""
    if not patterns:
        return True
    return any(PurePosixPath(path).full_match(pattern) for path in files for pattern in patterns)


def main(argv: list[str]) -> int:
    """Read a JSON list of changed files and write paths_match to GITHUB_OUTPUT."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", type=Path, help="JSON list of changed file paths")
    options = parser.parse_args(argv)
    try:
        patterns = parse_patterns(os.environ.get("PATH_PATTERNS", ""))
        files = json.loads(options.files.read_text(encoding="utf-8"))
        if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
            raise ValueError("the changed file list must be a JSON list of strings")
    except (OSError, ValueError) as error:
        print(f"error: {error}. Fix the paths input and rerun.", file=sys.stderr)
        return 1
    match = "true" if any_match(files, patterns) else "false"
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"paths_match={match}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

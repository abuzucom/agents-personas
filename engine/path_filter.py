#!/usr/bin/env python3
"""Decide whether a pull request touches any file a persona caller selected.

The caller passes newline-separated glob patterns. "**" crosses directory
levels and "*" stays inside one. Empty patterns select every pull request.

A pattern that starts with "!" excludes the files it matches. A changed file
counts when it matches an include pattern, or any file when no include
exists, and matches no exclusion. A pull request that touches only excluded
files skips the review.

SCAN_REQUESTED=true selects the pull request whatever the patterns say. The
workflow sets it when the pull request carries the <persona>-scan-requested
label.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path, PurePosixPath

MAX_PATTERNS = 100
MAX_PATTERN_CHARS = 256
EXCLUDE_PREFIX = "!"


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
        glob = pattern.removeprefix(EXCLUDE_PREFIX)
        if not glob:
            raise ValueError(f"pattern {pattern!r} needs a path after {EXCLUDE_PREFIX!r}")
        if glob.startswith("/") or ".." in glob.split("/"):
            raise ValueError(f"pattern {pattern!r} must be a relative repository path")
    return patterns


def _matches(path: str, globs: list[str]) -> bool:
    """Return whether one path matches any of the globs."""
    return any(PurePosixPath(path).full_match(glob) for glob in globs)


def any_match(files: list[str], patterns: list[str]) -> bool:
    """Return whether any changed file passes the includes and the exclusions."""
    if not patterns:
        return True
    includes = [pattern for pattern in patterns if not pattern.startswith(EXCLUDE_PREFIX)]
    excludes = [pattern.removeprefix(EXCLUDE_PREFIX) for pattern in patterns if pattern.startswith(EXCLUDE_PREFIX)]
    return any((not includes or _matches(path, includes)) and not _matches(path, excludes) for path in files)


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
    requested = os.environ.get("SCAN_REQUESTED") == "true"
    match = "true" if requested or any_match(files, patterns) else "false"
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"paths_match={match}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

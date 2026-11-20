"""Run the deterministic QUALITY.md prescan over an extracted head tree.

Ported from the prescan half of `abuzucom/euler` `ci/build_pr_case.py` at
9488a8c. The engine writes the head tree from git objects and passes its
directory here. The checks parse files and never execute them.
"""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quality_checks  # resolved through the path set above

HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,\d+)? @@")
PROJECT_CHECKS = [name for name, check in quality_checks.CHECKS.items() if check.project_check is not None]
FILE_CHECKS = [name for name in quality_checks.CHECKS if name not in PROJECT_CHECKS]
# Project-level classes report at line 1 and skip the added-lines filter.
PROJECT_CLASSES = {quality_checks.CHECKS[name].class_id for name in PROJECT_CHECKS}


def parse_added_lines(patch: str) -> list[int]:
    """Return head line numbers of added lines in one file patch."""
    added = []
    line_number = 0
    in_hunk = False
    for line in patch.splitlines():
        header = HUNK_HEADER.match(line)
        if header:
            line_number = int(header.group("start"))
            in_hunk = True
        elif not in_hunk:
            # The ---/+++ file headers precede the first hunk. Inside a hunk,
            # an added line with content that starts with "++" is still content.
            continue
        elif line.startswith("+"):
            added.append(line_number)
            line_number += 1
        elif line.startswith(" "):
            line_number += 1
    return added


def is_excluded(path: str, exclude: list[str]) -> bool:
    """Return True when a glob in exclude matches the path."""
    return any(fnmatch.fnmatch(path, pattern) for pattern in exclude)


def keep_finding(item: quality_checks.Finding, changed: set[str], added: dict[str, list[int]],
                 exclude: list[str]) -> bool:
    """Return True for findings in changed, non-excluded files on added lines."""
    if item.path not in changed or is_excluded(item.path, exclude):
        return False
    return item.class_id in PROJECT_CLASSES or item.line in added.get(item.path, [])


def present_paths(tree: Path, paths: list[str]) -> list[str]:
    """Return the paths that exist as regular files in the extracted tree."""
    return [path for path in paths if (tree / path).is_file()]


def remove_parser_limit_files(tree: Path, paths: list[str]) -> list[str]:
    """Delete the files that hit a parser limit from the extracted tree and return them.

    A child process runs the parse, so a MemoryError never reaches this
    process. Deleting the file keeps the file checks and the project checks
    from parsing it again.
    """
    failing = quality_checks.find_parser_limit_files([tree / path for path in paths])
    for path in failing:
        path.unlink()
    return [path.relative_to(tree).as_posix() for path in failing]


def build_prescan(tree: Path, changed: list[str], patches: dict[str, str],
                  exclude: list[str]) -> tuple[list[dict], list[str]]:
    """Return prescan candidates with global IDs and the scanned files that exhaust the parsers."""
    tree = Path(tree)
    added = {path: parse_added_lines(patch) for path, patch in patches.items()}
    scanned = [path for path in changed if path in patches and not is_excluded(path, exclude)]
    unparsed = remove_parser_limit_files(tree, present_paths(tree, scanned))
    present = [tree / path for path in present_paths(tree, scanned)]
    parse_failures: list[str] = []
    findings = quality_checks.run_checks(FILE_CHECKS, present, tree, changed=changed, parse_failures=parse_failures)
    findings += quality_checks.run_checks(PROJECT_CHECKS, [tree], tree, changed=changed)
    unparsed += [path for path in parse_failures if path not in unparsed]
    kept = [item for item in findings if keep_finding(item, set(changed), added, exclude)]
    prescan = [
        {"id": f"P{index}", "file": item.path, "line": item.line, "class": item.class_id,
         "message": item.message, "blocking": item.blocking}
        for index, item in enumerate(kept, 1)
    ]
    return prescan, unparsed

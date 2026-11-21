#!/usr/bin/env python3
"""Stage a pull request persona as data for the eval-live workflow.

The eval-live job holds the provider key and reads the pull request's
persona files. A symlink there could point at a runner file, and the eval
would send that file to the model. Python there would run with the key.
Staging therefore copies only regular files from <source>/reviewers/<persona>/
into <target>/reviewers/<persona>/, and drops Python outside eval/cases/.
A Python file under eval/cases/ is a review input that the eval reads as
text. A symlink,
a special file, an oversized file, or an unsafe persona name fails the run.
The grader comes from the default branch through run_eval --extension-root.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import sys
from pathlib import Path

PERSONA_NAME = re.compile(r"[a-z][a-z0-9-]{0,31}")
MAX_FILE_BYTES = 1_048_576
MAX_TOTAL_BYTES = 16_777_216
MAX_FILES = 2_000
# Python outside the case inputs is persona code. The default branch supplies it.
SKIPPED_SUFFIXES = (".py",)
CASE_INPUT_ROOT = Path("eval") / "cases"


class StageError(ValueError):
    """A persona tree the eval-live workflow refuses to stage."""


def _persona_dir(source: Path, persona: str) -> Path:
    """Return the source persona directory after the name and link checks."""
    if not PERSONA_NAME.fullmatch(persona):
        raise StageError(f"persona name {persona!r} must be lowercase letters, digits, and hyphens")
    reviewers = Path(source) / "reviewers"
    for path in (reviewers, reviewers / persona):
        if path.is_symlink():
            raise StageError(f"{path} is a symlink")
    persona_dir = reviewers / persona
    if not persona_dir.is_dir():
        raise StageError(f"no persona directory at {persona_dir}")
    return persona_dir


def _data_files(persona_dir: Path) -> list[Path]:
    """Return the data files below persona_dir, refusing links and special files."""
    files = []
    total = 0
    for directory, names, file_names in os.walk(persona_dir, followlinks=False):
        for name in sorted(names + file_names):
            path = Path(directory) / name
            status = path.lstat()
            if stat.S_ISLNK(status.st_mode):
                raise StageError(f"{path.relative_to(persona_dir)} is a symlink")
            if stat.S_ISDIR(status.st_mode):
                continue
            if not stat.S_ISREG(status.st_mode):
                raise StageError(f"{path.relative_to(persona_dir)} is not a regular file")
            if status.st_size > MAX_FILE_BYTES:
                raise StageError(f"{path.relative_to(persona_dir)} exceeds {MAX_FILE_BYTES} bytes")
            if path.suffix in SKIPPED_SUFFIXES and not path.relative_to(persona_dir).is_relative_to(CASE_INPUT_ROOT):
                continue
            total += status.st_size
            files.append(path)
    if len(files) > MAX_FILES or total > MAX_TOTAL_BYTES:
        raise StageError(f"the persona exceeds {MAX_FILES} files or {MAX_TOTAL_BYTES} bytes")
    return files


def stage(source: Path, persona: str, target: Path) -> Path:
    """Copy the persona data into target and return the staged persona directory."""
    persona_dir = _persona_dir(source, persona)
    staged = Path(target) / "reviewers" / persona
    if staged.exists() or staged.is_symlink():
        raise StageError(f"{staged} already exists")
    files = _data_files(persona_dir)
    for path in files:
        destination = staged / path.relative_to(persona_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination, follow_symlinks=False)
    return staged


def main(argv: list[str]) -> int:
    """Stage one persona from the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True, help="checkout of the pull request head")
    parser.add_argument("--persona", required=True)
    parser.add_argument("--target", type=Path, required=True, help="new root for the staged persona")
    options = parser.parse_args(argv)
    try:
        staged = stage(options.source, options.persona, options.target)
    except (StageError, OSError) as error:
        print(f"error: cannot stage the persona: {error}. Fix the pull request files and rerun.", file=sys.stderr)
        return 1
    print(f"staged {staged}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

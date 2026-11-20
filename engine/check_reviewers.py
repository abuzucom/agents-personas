#!/usr/bin/env python3
"""Validate every reviewers/<name>/reviewer.json, the template included."""
import argparse
import sys
from pathlib import Path

try:
    import reviewers
except ImportError:
    from engine import reviewers


def check_tree(root: Path) -> list[str]:
    """Return every finding across all persona directories."""
    directory = reviewers.reviewers_root(root)
    if not directory.is_dir():
        return ["reviewers/ is missing"]
    findings = []
    for persona_dir in sorted(path for path in directory.iterdir() if path.is_dir()):
        findings.extend(reviewers.validate_persona(persona_dir))
    return findings


def main(argv: list[str]) -> int:
    """Print findings and return 1 when any persona manifest is invalid."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root")
    options = parser.parse_args(argv)
    root = Path(options.root)
    findings = check_tree(root)
    if findings:
        for finding in findings:
            print(f"error: {finding}", file=sys.stderr)
        print("Fix each manifest named above, then rerun this check.", file=sys.stderr)
        return 1
    count = len(reviewers.list_personas(root))
    print(f"valid manifests: {count} persona(s) plus the template")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

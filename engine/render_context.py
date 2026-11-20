#!/usr/bin/env python3
"""Print one persona mode with context delivery for an agent prompt."""
import argparse
import sys
from pathlib import Path

try:
    import reviewers
except ImportError:
    from engine import reviewers


def render_context(root: Path, persona: str, mode: str) -> str:
    """Return the ASCII prompt text of one context-delivery mode."""
    persona_dir, manifest = reviewers.load_persona(root, persona)
    entry = manifest["modes"].get(mode)
    if entry is None:
        raise reviewers.ReviewerError(f"unknown mode '{mode}' for persona '{persona}'")
    if not entry.get("context"):
        raise reviewers.ReviewerError(f"mode '{mode}' has no context delivery")
    path = reviewers.prompt_path(persona_dir, entry["prompt"])
    content = path.read_bytes()
    if len(content) > reviewers.MAX_CONTEXT_BYTES:
        raise reviewers.ReviewerError(
            f"prompt '{entry['prompt']}' exceeds {reviewers.MAX_CONTEXT_BYTES} bytes")
    try:
        return content.decode("ascii")
    except UnicodeDecodeError as error:
        raise reviewers.ReviewerError(f"prompt '{entry['prompt']}' is not ASCII") from error


def main(argv: list[str]) -> int:
    """Write the rendered context to standard output."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--persona", required=True)
    parser.add_argument("--mode", required=True)
    options = parser.parse_args(argv)
    try:
        text = render_context(Path(options.root), options.persona, options.mode)
    except (OSError, reviewers.ReviewerError) as error:
        print(f"error: {error}. Choose a persona and a mode with context delivery.",
              file=sys.stderr)
        return 1
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

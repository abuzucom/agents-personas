#!/usr/bin/env python3
"""Print one persona mode with context delivery for an agent prompt."""

import argparse
import sys
from pathlib import Path

# The engine directory joins the import path, so these imports resolve
# both when a script runs directly and when a test loads it from a file.
_ENGINE_DIR = str(Path(__file__).resolve().parent)
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

import reviewers  # resolved through the path set above


def render_context(root: Path, persona: str, mode: str) -> bytes:
    """Return the ASCII prompt bytes of one context-delivery mode."""
    persona_dir, manifest = reviewers.load_persona(root, persona)
    entry = manifest["modes"].get(mode)
    if entry is None:
        raise reviewers.ReviewerError(f"unknown mode '{mode}' for persona '{persona}'")
    if not entry.get("context"):
        raise reviewers.ReviewerError(f"mode '{mode}' has no context delivery")
    separator = reviewers.PROMPT_SEPARATOR.encode("ascii")
    content = separator.join(path.read_bytes() for path in reviewers.prompt_paths(persona_dir, entry["prompt"]))
    if len(content) > reviewers.MAX_CONTEXT_BYTES:
        raise reviewers.ReviewerError(f"prompt '{entry['prompt']}' exceeds {reviewers.MAX_CONTEXT_BYTES} bytes")
    if not content.isascii():
        raise reviewers.ReviewerError(f"prompt '{entry['prompt']}' is not ASCII")
    return content


def main(argv: list[str]) -> int:
    """Write the rendered context to standard output."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--persona", required=True)
    parser.add_argument("--mode", required=True)
    options = parser.parse_args(argv)
    try:
        context_bytes = render_context(Path(options.root), options.persona, options.mode)
    except (OSError, reviewers.ReviewerError) as error:
        print(f"error: {error}. Choose a persona and a mode with context delivery.", file=sys.stderr)
        return 1
    # Text-mode standard output rewrites newlines on Windows. The binary
    # buffer keeps the rendered context identical on every platform.
    sys.stdout.buffer.write(context_bytes)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

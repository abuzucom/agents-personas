"""Load persona hook modules and check what they return.

A persona can ship reviewers/<name>/review_hooks.py with these optional
functions:

- trusted_context(head_dir, changed, patches, options) -> dict
  Runs in the build stage, which holds no provider key. head_dir holds the
  head tree as plain files. The engine never executes them. The result is
  {"context": {key: [item, ...]}, "unreviewed": [path, ...]}. Each item
  names a changed "file". Each chunk envelope carries the items of its own
  files under TRUSTED_CONTEXT[key].
- validate_reply(payload, response, envelope) -> list[str]
  Returns problems with a reply that passed the engine validator. A problem
  triggers the same single retry as an engine problem.
- forced_verdict(context) -> tuple[str, str] | None
  Returns a verdict and its reason that the run takes when it is more
  severe than the chunk verdicts.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REVIEW_HOOKS_NAME = "review_hooks.py"
CONTEXT_RESULT_KEYS = frozenset({"context", "unreviewed"})


def load_module(path: Path, module_name: str) -> ModuleType | None:
    """Return the module at path, or None when the file is absent.

    A symlink could point the engine at code outside the persona directory,
    so only a regular file loads.
    """
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path.name} must be a regular file")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_review_hooks(persona_dir: Path) -> ModuleType | None:
    """Return the review hooks of one persona, or None when it ships none."""
    persona_dir = Path(persona_dir)
    return load_module(persona_dir / REVIEW_HOOKS_NAME, f"review_hooks_{persona_dir.name}")


def _check_items(key: object, items: object, changed: set[str]) -> None:
    """Reject a context entry that is not a list of items on changed files."""
    if not isinstance(key, str) or not key:
        raise ValueError("trusted_context keys must be non-empty strings")
    if not isinstance(items, list) or not all(isinstance(item, dict) and isinstance(item.get("file"), str)
                                              for item in items):
        raise ValueError(f"trusted_context '{key}' must be a list of objects with a file")
    outside = sorted({item["file"] for item in items} - changed)
    if outside:
        raise ValueError(f"trusted_context '{key}' names files outside the changed files: {outside[:5]}")


def check_context_result(result: object, changed: list[str]) -> dict:
    """Return a trusted_context result after checking its shape."""
    if not isinstance(result, dict) or set(result) != CONTEXT_RESULT_KEYS:
        raise ValueError("trusted_context result is not an object with exactly the keys context and unreviewed")
    context, unreviewed = result["context"], result["unreviewed"]
    if not isinstance(context, dict):
        raise ValueError("trusted_context context must be an object")
    changed_set = set(changed)
    for key, items in context.items():
        _check_items(key, items, changed_set)
    if not isinstance(unreviewed, list) or not all(isinstance(path, str) and path in changed_set
                                                   for path in unreviewed):
        raise ValueError("trusted_context unreviewed must list changed files")
    return result


def chunk_context(context: dict, files: list[str]) -> dict:
    """Return the context items that belong to one chunk's files."""
    selected = set(files)
    return {key: [item for item in items if item["file"] in selected] for key, items in context.items()}

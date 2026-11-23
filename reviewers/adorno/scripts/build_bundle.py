#!/usr/bin/env python3
"""Concatenate documentation sources into paste-ready bundles.

The builder is manifest-driven and repo-agnostic. It knows nothing about
classes, checks, or scopes. abuzucom/foucault and abuzucom/havel adopt it
with their own bundles.json.

A scope declares one or more tiers. --check regenerates every bundle in
memory and fails on any byte difference without writing.
"""

import argparse
import json
import pathlib
import re
import sys
import tempfile

MANIFEST_FILENAME = "bundles.json"
OUTPUT_DIRECTORY = "bundles"
TIERS = ("standard", "full")
FULL_SUFFIX = "-full"
SEPARATOR = "\n\n---\n\n"
NUMERIC_PATTERN = re.compile(r"(\d+)")


class BundleError(Exception):
    """A manifest, a source path, or an output path is unusable."""


def load_manifest(root: pathlib.Path) -> dict:
    """Return the parsed manifest, or raise with a recovery action."""
    path = root / MANIFEST_FILENAME
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise BundleError(f"{MANIFEST_FILENAME}: cannot read ({error}). Create the manifest at the repository root.")
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise BundleError(f"{MANIFEST_FILENAME}: invalid JSON at line {error.lineno}. Correct the syntax.")
    if not isinstance(manifest, dict) or not manifest:
        raise BundleError(f"{MANIFEST_FILENAME}: expected a non-empty object mapping scope to tiers.")
    for scope, tiers in manifest.items():
        if not isinstance(tiers, dict) or not tiers:
            raise BundleError(f"{MANIFEST_FILENAME}: scope '{scope}' must map at least one tier to a source list.")
        # A scope declares the tiers it needs rather than all of them. A
        # repository whose hub carries one reference layer has one meaningful
        # bundle, and a second tier would commit a duplicate nobody pastes.
        for tier in tiers:
            if tier not in TIERS:
                raise BundleError(
                    f"{MANIFEST_FILENAME}: scope '{scope}' declares unknown tier "
                    f"'{tier}'. Use one of {', '.join(TIERS)}."
                )
    return manifest


def _sort_key(path: pathlib.Path):
    """Return a key ordering numeric filename segments numerically."""
    parts = NUMERIC_PATTERN.split(path.name)
    return tuple(int(part) if part.isdigit() else part for part in parts)


def resolve_sources(root: pathlib.Path, patterns) -> list:
    """Return the source files a pattern list names, in deterministic order."""
    # relative_to compares path text rather than filesystem identity, so an
    # unnormalized root makes every sound source read as one escaping the
    # root. Normalize before any comparison.
    root = root.resolve()
    resolved = []
    seen = set()
    for pattern in patterns:
        if "*" in pattern or "?" in pattern:
            matches = sorted(root.glob(pattern), key=_sort_key)
            if not matches:
                raise BundleError(
                    f"{MANIFEST_FILENAME}: glob '{pattern}' resolves no file. Add the missing files or remove the glob."
                )
        else:
            candidate = root / pattern
            if not candidate.is_file():
                raise BundleError(
                    f"{MANIFEST_FILENAME}: source '{pattern}' does not exist. Correct the path or add the file."
                )
            matches = [candidate]
        for match in matches:
            absolute = match.resolve()
            try:
                absolute.relative_to(root)
            except ValueError:
                raise BundleError(
                    f"{MANIFEST_FILENAME}: source '{pattern}' resolves outside the "
                    "repository root. Use a path inside the repository."
                )
            if absolute in seen:
                continue
            seen.add(absolute)
            resolved.append(absolute)
    return resolved


def output_path(root: pathlib.Path, scope: str, tier: str) -> pathlib.Path:
    """Return the bundle path for one scope and tier, inside bundles/."""
    suffix = FULL_SUFFIX if tier == "full" else ""
    root = root.resolve()
    link = root / OUTPUT_DIRECTORY
    # A symlinked bundles/ would carry every write to its target. resolve()
    # follows the link, so the check reads the unresolved entry first.
    if link.is_symlink():
        raise BundleError(f"{OUTPUT_DIRECTORY}/ is a symlink. Replace it with a directory inside the repository.")
    directory = link.resolve()
    if directory.parent != root:
        raise BundleError(f"{OUTPUT_DIRECTORY}/ resolves outside the repository root. Use a directory inside it.")
    candidate = (directory / f"{scope}{suffix}.md").resolve()
    if candidate.parent != directory:
        raise BundleError(
            f"scope '{scope}' resolves outside {OUTPUT_DIRECTORY}/. Use a scope name without a path separator."
        )
    return candidate


def _header(scope: str, tier: str, sources) -> str:
    """Return the bundle header stating scope, tier, and source order."""
    names = "\n".join(f"- `{name}`" for name in sources)
    pointer = (
        "Each `Detail:` pointer resolves to a section further down this file."
        if tier == "full"
        else "Each `Detail:` pointer resolves to a repository path outside this file."
    )
    return (
        f"# Adorno audit bundle: {scope} ({tier} tier)\n\n"
        "Generated by `scripts/build_bundle.py`. Do not edit. Edit the sources\n"
        "and rebuild.\n\n"
        f"{pointer}\n\n"
        "Sources in order:\n\n"
        f"{names}\n"
    )


def render(root: pathlib.Path, scope: str, tier: str, manifest: dict, cache: dict | None = None) -> str:
    """Return the rendered bundle text for one scope and tier."""
    if scope not in manifest:
        raise BundleError(f"scope '{scope}' is absent from {MANIFEST_FILENAME}. Add it or correct the name.")
    if tier not in manifest[scope]:
        raise BundleError(
            f"scope '{scope}' does not declare the '{tier}' tier. Add it to "
            f"{MANIFEST_FILENAME} or ask for a tier the scope declares."
        )
    if cache is None:
        cache = {}
    root = root.resolve()
    sources = resolve_sources(root, manifest[scope][tier])
    # as_posix keeps the separator forward-slashed on every platform. str()
    # yields backslashes on Windows, so a rebuild there would change every
    # header line and report the whole tree stale.
    names = [path.relative_to(root).as_posix() for path in sources]
    parts = [_header(scope, tier, names)]
    for path in sources:
        if path not in cache:
            try:
                cache[path] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as error:
                raise BundleError(f"{path.relative_to(root)}: not valid UTF-8 ({error.reason}). Correct the encoding.")
            except OSError as error:
                raise BundleError(f"{path.relative_to(root)}: cannot read ({error}). Restore the file.")
        parts.append(cache[path].rstrip("\n"))
    return SEPARATOR.join(parts) + "\n"


def _write_atomically(destination: pathlib.Path, text: str) -> None:
    """Write through a temporary file in the destination directory."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: pathlib.Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=destination.parent, delete=False, suffix=".tmp"
        ) as handle:
            temp_path = pathlib.Path(handle.name)
            handle.write(text)
        # NamedTemporaryFile creates mode 600. A committed artifact needs the
        # ordinary file mode so a checkout is readable.
        temp_path.chmod(0o644)
        temp_path.replace(destination)
    except OSError:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def main(argv=None) -> int:
    """Build or check every bundle and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="repository root")
    parser.add_argument("--check", action="store_true", help="compare without writing")
    arguments = parser.parse_args(argv)
    root = pathlib.Path(arguments.root).resolve()

    try:
        manifest = load_manifest(root)
    except BundleError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    cache: dict = {}
    stale = []
    written = 0
    for scope in sorted(manifest):
        for tier in sorted(manifest[scope]):
            try:
                text = render(root, scope, tier, manifest, cache)
                destination = output_path(root, scope, tier)
            except BundleError as error:
                print(f"error: {error}", file=sys.stderr)
                return 1
            if arguments.check:
                current = destination.read_text(encoding="utf-8") if destination.is_file() else None
                if current != text:
                    stale.append(str(destination.relative_to(root)))
                continue
            _write_atomically(destination, text)
            written += 1

    if arguments.check:
        for name in stale:
            print(
                f"error: {name} does not match its sources. Run scripts/build_bundle.py and commit the result.",
                file=sys.stderr,
            )
        return 1 if stale else 0
    print(f"wrote {written} bundles")
    return 0


if __name__ == "__main__":
    sys.exit(main())

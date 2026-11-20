#!/usr/bin/env python3
"""Build fenced review envelopes for one pull request mode.

Ported from `abuzucom/euler` `ci/build_pr_case.py`. A persona trusted_context
hook, such as the euler prescan, reads the head tree as plain files.
The builder reads the base-to-head diff from git objects and never checks
out the head. It splits large diffs by file into chunks under the mode's
byte budget. Binary files, undecodable paths, overlong paths, single files
over the budget, and files past the chunk limit become unreviewed files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import envelope
    import persona_hooks
    import reviewers
except ImportError:
    from engine import envelope, persona_hooks, reviewers

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
LS_TREE_FIELDS = 3
CAT_FILE_HEADER_FIELDS = 3
# Symlinks (120000) and submodules (160000) stay unwritten.
REGULAR_FILE_MODES = frozenset({b"100644", b"100755"})
TRUSTED_CONTEXT_NAME = "trusted_context.json"
# json.dumps wraps a string in two quote bytes.
JSON_QUOTE_BYTES = 2
BINARY_NUMSTAT = b"-"
# numstat rows hold added, deleted, and path fields.
NUMSTAT_SPLITS = 2
PATCH_HEADER = b"diff --git "
PATCH_SEPARATOR = b"\n" + PATCH_HEADER
JSON_INDENT = 2
# A path longer than this stays out of the envelope. The cap bounds the
# author-controlled bytes a single name can place in front of the model.
MAX_PATH_CHARS = 1024


@dataclass(frozen=True)
class BuildOptions:
    """Inputs for one envelope build."""

    repo: Path
    base: str
    head: str
    out_dir: Path
    persona: str
    mode: str
    title: str
    body: str
    pr_number: int
    max_chunks: int
    max_envelope_bytes: int
    hooks: Any = None
    persona_options: dict = field(default_factory=dict)


def run_git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    """Run git with an argument array and return raw stdout.

    GIT_LITERAL_PATHSPECS stops a pull request path such as '*' from acting as a pattern.
    """
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("git not found on PATH. Install git before the build.")
    environment = {**os.environ, "GIT_LITERAL_PATHSPECS": "1"}
    result = subprocess.run([executable, "-C", str(repo), *args], input=stdin, capture_output=True,
                            check=False, env=environment)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {args[0]} failed: {detail}. Fetch both revisions before the build.")
    return result.stdout


def decode_paths(raw_paths: list[bytes]) -> tuple[list[str], list[str]]:
    """Split git paths into UTF-8 names and replacement-decoded undecodable names."""
    paths: list[str] = []
    undecodable: list[str] = []
    for item in raw_paths:
        try:
            paths.append(item.decode("utf-8"))
        except UnicodeDecodeError:
            undecodable.append(item.decode("utf-8", errors="replace"))
    return paths, undecodable


def read_binary_paths(options: BuildOptions) -> set[str]:
    """Return the changed paths that git reports as binary."""
    raw = run_git(options.repo, "diff", "-z", "--numstat", "--no-renames", options.base, options.head)
    binary = set()
    for record in raw.split(b"\0"):
        fields = record.split(b"\t", NUMSTAT_SPLITS)
        if len(fields) == NUMSTAT_SPLITS + 1 and fields[0] == BINARY_NUMSTAT:
            binary.add(fields[NUMSTAT_SPLITS].decode("utf-8", errors="replace"))
    return binary


def split_raw_and_patches(output: bytes) -> tuple[list[bytes], list[bytes]]:
    """Split 'git diff -z --raw -p' output into raw record paths and per-file patches.

    Each raw record is ':<modes> <ids> <status>' and a path, both NUL-terminated. One more NUL precedes
    the patches. Patch content lines start with ' ', '+', '-', or a backslash, so a line starting with
    'diff --git ' always opens the next file.
    """
    paths = []
    offset = 0
    while output.startswith(b":", offset):
        meta_end = output.index(b"\0", offset)
        path_end = output.index(b"\0", meta_end + 1)
        paths.append(output[meta_end + 1:path_end])
        offset = path_end + 1
    section = output[offset + 1:] if output.startswith(b"\0", offset) else output[offset:]
    if not section:
        return paths, []
    pieces = section.split(PATCH_SEPARATOR)
    patches = [pieces[0], *(PATCH_HEADER + piece for piece in pieces[1:])]
    # Every piece but the last lost its trailing newline to the split.
    return paths, [patch + b"\n" for patch in patches[:-1]] + patches[-1:]


def read_diff(options: BuildOptions) -> tuple[list[str], set[str], dict[str, str], list[str]]:
    """Return changed paths, binary paths, per-file text patches, and undecodable paths."""
    output = run_git(options.repo, "diff", "-z", "--raw", "-p", "--no-renames", "--no-color",
                     options.base, options.head)
    try:
        raw_paths, raw_patches = split_raw_and_patches(output)
    except ValueError as error:
        raise RuntimeError("git diff output is malformed. Rerun the build.") from error
    paths, undecodable = decode_paths(raw_paths)
    binary = read_binary_paths(options)
    by_path = dict(zip(raw_paths, raw_patches, strict=False))
    patches = {
        path: by_path.get(path.encode("utf-8"), b"").decode("utf-8", errors="replace")
        for path in paths if path not in binary
    }
    return paths + undecodable, binary, patches, undecodable


def split_unreviewable(patches: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Return reviewable patches and the paths that are empty or overlong."""
    kept = {path: patch for path, patch in patches.items() if patch and len(path) <= MAX_PATH_CHARS}
    return kept, [path for path in patches if path not in kept]


def limit_chunks(chunks: list[list[str]], max_chunks: int) -> tuple[list[list[str]], list[str]]:
    """Return the first max_chunks chunks and the files of the chunks past the limit."""
    return chunks[:max_chunks], [path for chunk in chunks[max_chunks:] for path in chunk]


def escaped_size(text: str) -> int:
    """Return the UTF-8 byte length of text inside a serialized envelope string."""
    return len(json.dumps(text, ensure_ascii=False).encode("utf-8")) - JSON_QUOTE_BYTES


def pack_chunks(patches: dict[str, str], budget: int,
                measure: Callable[[str], int] = len) -> tuple[list[list[str]], list[str]]:
    """Group files into chunks under the budget. Return chunks and oversized files."""
    chunks: list[list[str]] = []
    oversized = []
    current: list[str] = []
    size = 0
    for path, patch in patches.items():
        cost = measure(patch)
        if cost > budget:
            oversized.append(path)
            continue
        if current and size + cost > budget:
            chunks.append(current)
            current, size = [], 0
        current.append(path)
        size += cost
    if current:
        chunks.append(current)
    return chunks, oversized


def chunk_metadata(options: BuildOptions, chunk: str, changed: list[str], unreviewed: list[str]) -> dict:
    """Return the trusted metadata for one envelope."""
    return {"pr_number": options.pr_number, "base_sha": options.base, "head_sha": options.head,
            "chunk": chunk, "changed_files": changed, "unreviewed": unreviewed}


def chunk_metadata_bound(base: str, head: str, pr_number: int, max_chunks: int, paths: list[str]) -> dict:
    """Return metadata at its largest size: the widest chunk label and every path unreviewed."""
    return {"pr_number": pr_number, "base_sha": base, "head_sha": head,
            "chunk": f"{max_chunks}/{max_chunks}", "changed_files": paths, "unreviewed": paths}


def list_head_blobs(repo: Path, head: str) -> list[tuple[str, str]]:
    """Return object ID and path pairs for the regular files in the head tree."""
    raw = run_git(repo, "ls-tree", "-r", "-z", "--full-tree", head)
    blobs = []
    for record in raw.split(b"\0"):
        # The first tab separates metadata from the path. Tabs in names stay in the path.
        meta, _, raw_path = record.partition(b"\t")
        fields = meta.split(b" ")
        if len(fields) != LS_TREE_FIELDS or fields[0] not in REGULAR_FILE_MODES:
            continue
        try:
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            # read_diff already lists an undecodable changed path as unreviewed.
            continue
        blobs.append((fields[2].decode("ascii"), path))
    return blobs


def read_blobs(repo: Path, object_ids: list[str]) -> list[bytes]:
    """Return blob bodies in request order from one git cat-file --batch call.

    Each object arrives as an '<id> <type> <size>' header line, exactly size
    body bytes, and one newline. The size locates the next header, so a
    newline inside a body never shifts the parse.
    """
    request = "".join(f"{object_id}\n" for object_id in object_ids).encode("ascii")
    output = run_git(repo, "cat-file", "--batch", stdin=request)
    bodies = []
    offset = 0
    for object_id in object_ids:
        header_end = output.index(b"\n", offset)
        header = output[offset:header_end].split(b" ")
        if len(header) != CAT_FILE_HEADER_FIELDS or header[1] != b"blob":
            raise RuntimeError(f"git cat-file returned no blob for {object_id}. Fetch the head revision.")
        start = header_end + 1
        end = start + int(header[2])
        bodies.append(output[start:end])
        offset = end + 1
    if offset != len(output):
        raise RuntimeError(f"git cat-file output has {len(output) - offset} unparsed trailing bytes.")
    return bodies


def extract_head(repo: Path, head: str, target: Path) -> None:
    """Write the head tree's regular files into target straight from git objects.

    git archive would apply the head commit's export-ignore and export-subst
    attributes. A pull request could then hide or rewrite files before a
    hook reads them.
    """
    blobs = list_head_blobs(repo, head)
    root = Path(target).resolve()
    destinations = [(root / path).resolve() for _, path in blobs]
    # Check every destination before the first write.
    for (_, path), destination in zip(blobs, destinations, strict=True):
        if not destination.is_relative_to(root):
            raise RuntimeError(f"head tree path {path!r} escapes the extraction directory. Review it by hand.")
    for destination, body in zip(destinations, read_blobs(repo, [object_id for object_id, _ in blobs]),
                                 strict=True):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)


def collect_trusted_context(options: BuildOptions, changed: list[str], patches: dict[str, str]) -> dict:
    """Return the persona hook context, or an empty result without a hook."""
    hook = getattr(options.hooks, "trusted_context", None)
    if hook is None:
        return {"context": {}, "unreviewed": []}
    with tempfile.TemporaryDirectory() as directory:
        tree = Path(directory)
        extract_head(options.repo, options.head, tree)
        result = hook(tree, list(changed), dict(patches), dict(options.persona_options))
    return persona_hooks.check_context_result(result, changed)


def chunk_budget(options: BuildOptions, changed: list[str], context: dict | None = None) -> int:
    """Return the per-chunk patch budget in escaped UTF-8 bytes.

    The skeleton holds every path, the largest metadata, and empty patches.
    Each chunk envelope holds a subset of that content plus its patches.
    """
    metadata = chunk_metadata_bound(options.base, options.head, options.pr_number,
                                    options.max_chunks, changed)
    skeleton = envelope.build_envelope(options.persona, options.mode, dict.fromkeys(changed, ""),
                                       options.title, options.body, metadata, context=context)
    budget = options.max_envelope_bytes - len(skeleton.encode("utf-8"))
    if budget < 1:
        raise ValueError(f"the pull request text and file list fill the {options.max_envelope_bytes}-byte "
                         "envelope budget. Shorten the pull request body or split the pull request.")
    return budget


def validate_options(options: BuildOptions) -> None:
    """Reject revisions and limits the builder cannot use."""
    for revision in (options.base, options.head):
        if not FULL_SHA.match(revision):
            raise ValueError(f"revision {revision!r} is not a full lowercase commit SHA")
    if options.max_chunks < 1:
        raise ValueError(f"max_chunks {options.max_chunks} is below 1. Pass a positive chunk limit.")


def write_text_lf(path: Path, text: str) -> None:
    """Write UTF-8 text with LF line endings on every platform.

    Windows text mode would turn each newline into CRLF and push an envelope
    past the byte budget the builder measured.
    """
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, data: object) -> None:
    """Write JSON with a trailing newline."""
    write_text_lf(path, json.dumps(data, indent=JSON_INDENT) + "\n")


def build(options: BuildOptions) -> None:
    """Write envelopes and manifest.json to the output directory."""
    validate_options(options)
    changed, binary, patches, undecodable = read_diff(options)
    patches, unreviewable = split_unreviewable(patches)
    trusted = collect_trusted_context(options, changed, patches)
    # The skeleton holds every context item, so each chunk subset fits too.
    budget = chunk_budget(options, changed, trusted["context"])
    chunks, oversized = pack_chunks(patches, budget, escaped_size)
    chunks, overflow = limit_chunks(chunks, options.max_chunks)
    unreviewed = sorted(binary) + undecodable + unreviewable + oversized + overflow
    unreviewed += [path for path in trusted["unreviewed"] if path not in unreviewed]
    envelopes_dir = options.out_dir / "envelopes"
    envelopes_dir.mkdir(parents=True, exist_ok=True)
    manifest_chunks = []
    for index, files in enumerate(chunks, 1):
        metadata = chunk_metadata(options, f"{index}/{len(chunks)}", changed, unreviewed)
        text = envelope.build_envelope(options.persona, options.mode,
                                       {path: patches[path] for path in files},
                                       options.title, options.body, metadata,
                                       context=persona_hooks.chunk_context(trusted["context"], files))
        if len(text.encode("utf-8")) > options.max_envelope_bytes:
            raise RuntimeError(f"envelope {index} exceeds {options.max_envelope_bytes} bytes. "
                               "Lower max_envelope_bytes and rerun.")
        name = f"{index:03d}.json"
        write_text_lf(envelopes_dir / name, text)
        manifest_chunks.append({"envelope": name, "files": files})
    write_json(options.out_dir / TRUSTED_CONTEXT_NAME, trusted["context"])
    write_json(options.out_dir / "manifest.json", {
        "persona": options.persona, "mode": options.mode, "pr_number": options.pr_number,
        "base_sha": options.base, "head_sha": options.head, "changed_files": changed,
        "unreviewed": unreviewed, "chunks": manifest_chunks,
    })


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    """Return parsed command line options."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="agents-personas checkout that holds reviewers/")
    parser.add_argument("--persona", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-chunks", type=int, help="request a lower chunk cap")
    parser.add_argument("--max-envelope-bytes", type=int, help="request a lower envelope byte cap")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """Build envelopes from command line options and environment pull request text."""
    args = parse_arguments(argv)
    requested = {name: value for name, value in (("max_chunks", args.max_chunks),
                                                 ("max_envelope_bytes", args.max_envelope_bytes))
                 if value is not None}
    try:
        _persona_dir, manifest = reviewers.load_persona(args.root, args.persona)
        reviewers.resolve_review_modes(manifest, args.mode)
        caps = reviewers.resolve_caps(manifest["modes"][args.mode], requested)
        for name in caps["clamped"]:
            sys.stderr.write(f"notice: requested {name} exceeds the mode cap. The mode cap applies.\n")
        build(BuildOptions(
            repo=args.repo, base=args.base, head=args.head, out_dir=args.out_dir,
            persona=args.persona, mode=args.mode, title=os.environ.get("PR_TITLE", ""),
            body=os.environ.get("PR_BODY", ""), pr_number=args.pr_number,
            max_chunks=caps["max_chunks"], max_envelope_bytes=caps["max_envelope_bytes"],
        ))
    except (ValueError, RuntimeError) as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Build fenced review envelopes for one pull request mode.

Ported from `abuzucom/euler` `ci/build_pr_case.py`. A persona case_context
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
# git ls-tree -l prints mode, type, object, and size before the path.
LS_TREE_LONG_FIELDS = 4
# Head extraction caps. A larger blob stays unwritten. A larger tree skips the
# persona hook. A read batch bounds the bytes one git call returns.
MAX_HEAD_BLOB_BYTES = 1024 * 1024
MAX_HEAD_TREE_BYTES = 64 * 1024 * 1024
HEAD_READ_BATCH_BYTES = 8 * 1024 * 1024
# The tree listing caps bound memory before any blob size is known.
MAX_HEAD_TREE_ENTRIES = 100_000
MAX_HEAD_LISTING_BYTES = 16 * 1024 * 1024
LISTING_READ_BYTES = 64 * 1024
CAT_FILE_HEADER_FIELDS = 3
# Symlinks (120000) and submodules (160000) stay unwritten.
REGULAR_FILE_MODES = frozenset({b"100644", b"100755"})
CASE_CONTEXT_NAME = "case_context.json"
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
    max_blob_bytes: int = MAX_HEAD_BLOB_BYTES
    max_tree_bytes: int = MAX_HEAD_TREE_BYTES


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


def diff_range(options: BuildOptions) -> str:
    """Return the three-dot range from the merge base of base and head to head.

    The workflow passes the current tip of the base branch. After that branch
    moves, base..head would show its newer commits in reverse, as if the pull
    request undid those commits. GitHub's pull request diff starts at the
    merge base.
    """
    return f"{options.base}...{options.head}"


def read_binary_paths(options: BuildOptions) -> set[str]:
    """Return the changed paths that git reports as binary."""
    raw = run_git(options.repo, "diff", "-z", "--numstat", "--no-renames", diff_range(options))
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
                     diff_range(options))
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
    """Return the trusted metadata for one envelope. The path lists ride in REVIEW_TARGET."""
    return {"pr_number": options.pr_number, "base_sha": options.base, "head_sha": options.head,
            "chunk": chunk, "changed_file_count": len(changed), "unreviewed_count": len(unreviewed)}


def chunk_metadata_bound(base: str, head: str, pr_number: int, max_chunks: int, paths: list[str]) -> dict:
    """Return metadata at its largest size: the widest chunk label and every path unreviewed."""
    return {"pr_number": pr_number, "base_sha": base, "head_sha": head,
            "chunk": f"{max_chunks}/{max_chunks}", "changed_file_count": len(paths), "unreviewed_count": len(paths)}


class HeadTreeTooLarge(RuntimeError):
    """The head tree holds more bytes than the extraction budget."""


def _parse_tree_record(record: bytes) -> tuple[str, str, int] | None:
    """Return object ID, path, and size for one regular-file ls-tree record."""
    # The first tab separates metadata from the path. Tabs in names stay in the path.
    meta, _, raw_path = record.partition(b"\t")
    # git pads the size column with spaces, so split on any run of them.
    fields = meta.split()
    if len(fields) != LS_TREE_LONG_FIELDS or fields[0] not in REGULAR_FILE_MODES:
        return None
    try:
        path = raw_path.decode("utf-8")
    except UnicodeDecodeError:
        # read_diff already lists an undecodable changed path as unreviewed.
        return None
    return fields[2].decode("ascii"), path, int(fields[3])


def list_head_blobs(repo: Path, head: str, max_entries: int = MAX_HEAD_TREE_ENTRIES,
                    max_listing_bytes: int = MAX_HEAD_LISTING_BYTES) -> list[tuple[str, str, int]]:
    """Return object ID, path, and size for the regular files in the head tree.

    The listing streams through a pipe. A tree past either cap stops the read
    before the whole listing reaches memory.
    """
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("git not found on PATH. Install git before the build.")
    command = [executable, "-C", str(repo), "ls-tree", "-r", "-z", "-l", "--full-tree", head]
    environment = {**os.environ, "GIT_LITERAL_PATHSPECS": "1"}
    blobs, pending, entries, read = [], b"", 0, 0
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment) as process:
        try:
            for chunk in iter(lambda: process.stdout.read(LISTING_READ_BYTES), b""):
                read += len(chunk)
                if read > max_listing_bytes:
                    raise HeadTreeTooLarge(f"the head tree listing exceeds {max_listing_bytes} bytes")
                *records, pending = (pending + chunk).split(b"\0")
                entries += len(records)
                if entries > max_entries:
                    raise HeadTreeTooLarge(f"the head tree holds more than {max_entries} entries")
                blobs += [blob for blob in map(_parse_tree_record, records) if blob is not None]
        except HeadTreeTooLarge:
            process.kill()
            raise
    if process.returncode != 0:
        raise RuntimeError("git ls-tree failed. Fetch the head revision before the build.")
    # -z ends every record with NUL. A final record without one still counts.
    tail = _parse_tree_record(pending) if pending else None
    return blobs + ([tail] if tail else [])


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


def _read_batches(blobs: list[tuple[str, str, int]], batch_bytes: int) -> list[list[tuple[str, str, int]]]:
    """Group blobs so one cat-file call holds at most batch_bytes, or one blob."""
    batches, current, size = [], [], 0
    for blob in blobs:
        if current and size + blob[2] > batch_bytes:
            batches.append(current)
            current, size = [], 0
        current.append(blob)
        size += blob[2]
    if current:
        batches.append(current)
    return batches


def extract_head(repo: Path, head: str, target: Path, max_blob_bytes: int = MAX_HEAD_BLOB_BYTES,
                 max_tree_bytes: int = MAX_HEAD_TREE_BYTES, batch_bytes: int = HEAD_READ_BATCH_BYTES) -> list[str]:
    """Write the head tree's regular files into target and return the skipped oversized paths.

    git archive would apply the head commit's export-ignore and export-subst
    attributes. A pull request could then hide or rewrite files before a
    hook reads them. The caps bound memory and disk. A pull request cannot
    make the build read an unbounded tree.
    """
    blobs = list_head_blobs(repo, head)
    skipped = sorted(path for _, path, size in blobs if size > max_blob_bytes)
    kept = [blob for blob in blobs if blob[2] <= max_blob_bytes]
    total = sum(size for _, _, size in kept)
    if total > max_tree_bytes:
        raise HeadTreeTooLarge(f"the head tree holds {total} bytes and exceeds the {max_tree_bytes}-byte budget")
    root = Path(target).resolve()
    destinations = {path: (root / path).resolve() for _, path, _ in kept}
    # Check every destination before the first write.
    for path, destination in destinations.items():
        if not destination.is_relative_to(root):
            raise RuntimeError(f"head tree path {path!r} escapes the extraction directory. Review it by hand.")
    for batch in _read_batches(kept, batch_bytes):
        for (_, path, _), body in zip(batch, read_blobs(repo, [object_id for object_id, _, _ in batch]),
                                      strict=True):
            destinations[path].parent.mkdir(parents=True, exist_ok=True)
            destinations[path].write_bytes(body)
    return skipped


def collect_case_context(options: BuildOptions, changed: list[str], patches: dict[str, str]) -> dict:
    """Return the persona hook context, or an empty result without a hook.

    A tree over the budget skips the hook and marks every changed file
    unreviewed. A changed file over the per-file cap becomes unreviewed.
    """
    hook = getattr(options.hooks, "case_context", None)
    if hook is None:
        return {"context": {}, "unreviewed": []}
    with tempfile.TemporaryDirectory() as directory:
        tree = Path(directory)
        try:
            skipped = extract_head(options.repo, options.head, tree, options.max_blob_bytes, options.max_tree_bytes)
        except HeadTreeTooLarge:
            return {"context": {}, "unreviewed": list(changed)}
        result = hook(tree, list(changed), dict(patches), dict(options.persona_options))
    result = persona_hooks.check_context_result(result, changed)
    skipped_paths = set(skipped)
    oversized = [path for path in changed if path in skipped_paths and path not in result["unreviewed"]]
    return {"context": result["context"], "unreviewed": result["unreviewed"] + oversized}


def chunk_budget(options: BuildOptions, changed: list[str], context: dict | None = None) -> int:
    """Return the per-chunk patch budget in escaped UTF-8 bytes.

    The skeleton holds every path, the largest metadata, and empty patches.
    Each chunk envelope holds a subset of that content plus its patches.
    """
    metadata = chunk_metadata_bound(options.base, options.head, options.pr_number,
                                    options.max_chunks, changed)
    skeleton = envelope.build_envelope(options.persona, options.mode, dict.fromkeys(changed, ""),
                                       options.title, options.body, metadata, context=context,
                                       changed_files=changed, unreviewed=changed)
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


def options_digest(persona_options: dict) -> str:
    """Return the SHA-256 of the resolved persona options in canonical JSON."""
    return envelope.digest(persona_options)


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
    hook_context = collect_case_context(options, changed, patches)
    # The skeleton holds every context item, so each chunk subset fits too.
    budget = chunk_budget(options, changed, hook_context["context"])
    chunks, oversized = pack_chunks(patches, budget, escaped_size)
    chunks, overflow = limit_chunks(chunks, options.max_chunks)
    unreviewed = sorted(binary) + undecodable + unreviewable + oversized + overflow
    unreviewed += [path for path in hook_context["unreviewed"] if path not in unreviewed]
    envelopes_dir = options.out_dir / "envelopes"
    envelopes_dir.mkdir(parents=True, exist_ok=True)
    manifest_chunks = []
    for index, files in enumerate(chunks, 1):
        metadata = chunk_metadata(options, f"{index}/{len(chunks)}", changed, unreviewed)
        text = envelope.build_envelope(options.persona, options.mode,
                                       {path: patches[path] for path in files},
                                       options.title, options.body, metadata,
                                       context=persona_hooks.chunk_context(hook_context["context"], files),
                                       changed_files=changed, unreviewed=unreviewed)
        if len(text.encode("utf-8")) > options.max_envelope_bytes:
            raise RuntimeError(f"envelope {index} exceeds {options.max_envelope_bytes} bytes. "
                               "Lower max_envelope_bytes and rerun.")
        name = f"{index:03d}.json"
        write_text_lf(envelopes_dir / name, text)
        manifest_chunks.append({"envelope": name, "files": files})
    write_json(options.out_dir / CASE_CONTEXT_NAME, hook_context["context"])
    write_json(options.out_dir / "manifest.json", {
        "persona": options.persona, "mode": options.mode, "pr_number": options.pr_number,
        "max_chunks": options.max_chunks, "max_envelope_bytes": options.max_envelope_bytes,
        "persona_options_sha256": options_digest(options.persona_options),
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

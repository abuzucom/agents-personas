#!/usr/bin/env python3
"""Build and check the files of one tagged agents-personas version.

The repository owner pushes a vX.Y.Z tag on a main commit.
.github/workflows/release.yml then runs these subcommands from the repository
root:

    python tools/release_personas.py check-tag v0.21.0
    python tools/release_personas.py archive 0.21.0 <asset-folder>
    python tools/release_personas.py check-assets <asset-folder> 0.21.0
    python tools/release_personas.py checksums <asset-folder>
    python tools/release_personas.py notes 0.21.0 <commit-sha> <output-file>

check-tag fails unless the tag equals "v" plus the top CHANGELOG.md version.
archive writes a tar.gz of the committed HEAD tree. The gzip header holds no
time and no file name, so each build of one commit yields identical bytes. A
rerun of the workflow therefore matches the archive already on the draft.
check-assets fails unless a folder holds exactly the expected files.
checksums writes SHA256SUMS.txt in the sha256sum format.
notes writes the CHANGELOG section of one version, then the caller pin block.
Callers pin full commit SHAs, so the pin block names the tagged commit.
"""

import argparse
import gzip
import hashlib
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
TAG_PREFIX = "v"
CHANGELOG_FILE = "CHANGELOG.md"
CHECKSUM_FILE = "SHA256SUMS.txt"
ARCHIVE_STEM = "agents-personas"
BUNDLE_SUFFIX = ".sigstore.json"
REPOSITORY = "abuzucom/agents-personas"
CHECK_FAILED = 1
GIT_TIMEOUT_SECONDS = 120
HASH_CHUNK_BYTES = 1024 * 1024
# The gzip header time stays zero for byte-identical rebuilds.
GZIP_MTIME = 0
GZIP_LEVEL = 9
VERSION_PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
COMMIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
CHANGELOG_HEADING = re.compile(r"^## \[([^\]\n]*)\]", re.MULTILINE)
# The wrapper workflows that callers pin, in docs/migration.md order.
CALLER_WORKFLOWS = (
    "foucault-security-review.yml",
    "euler-quality-review.yml",
    "adorno-ui-review.yml",
    "generay-time-review.yml",
    "havel-privacy-review.yml",
)
PIN_NOTES_HEADER = """\
## Pin this version

Pin `uses:` and `personas_ref` to the same full commit SHA. A tag or branch
name fails validation. `docs/migration.md` covers the caller inputs.

```yaml
"""


def require_version(text: str) -> str:
    """Return a X.Y.Z version, or raise ValueError on any other text."""
    if not VERSION_PATTERN.fullmatch(text):
        raise ValueError(f"{text!r} is not a X.Y.Z version without leading zeros.")
    return text


def archive_name(version: str) -> str:
    """Return the archive file name of one version."""
    return f"{ARCHIVE_STEM}-{version}.tar.gz"


def bundle_name(version: str) -> str:
    """Return the Sigstore bundle file name of one version's archive."""
    return archive_name(version) + BUNDLE_SUFFIX


def read_top_version(changelog: str) -> str:
    """Return the version of the first CHANGELOG heading, or an empty string."""
    match = CHANGELOG_HEADING.search(changelog)
    if match is None:
        return ""
    return match.group(1)


def find_tag_problems(tag: str, root: Path) -> list[str]:
    """Return one line per reason the tag differs from the changelog."""
    if not tag.startswith(TAG_PREFIX):
        return [f"Tag {tag!r} lacks the {TAG_PREFIX!r} prefix. Push a vX.Y.Z tag."]
    version = tag[len(TAG_PREFIX) :]
    if not VERSION_PATTERN.fullmatch(version):
        return [f"Tag {tag!r} is not vX.Y.Z without leading zeros. Push a vX.Y.Z tag."]
    path = root / CHANGELOG_FILE
    if not path.is_file():
        return [f"{CHANGELOG_FILE} is missing. Tag a commit that holds it."]
    top = read_top_version(path.read_text(encoding="utf-8"))
    if top != version:
        mismatch = f"{CHANGELOG_FILE} names {top!r} at the top, but the tag names {version!r}."
        return [f"{mismatch} Tag the commit whose top entry matches."]
    return []


def _require_empty_folder(folder: Path) -> None:
    """Raise ValueError unless the folder exists and holds nothing."""
    if not folder.is_dir():
        raise ValueError(f"{folder} is not a folder. Create it first.")
    if any(folder.iterdir()):
        raise ValueError(f"{folder} is not empty. Pass an empty folder.")


def _read_head_tar(root: Path, version: str) -> bytes:
    """Return the uncompressed git archive of HEAD with the version prefix."""
    prefix = f"{ARCHIVE_STEM}-{version}/"
    result = subprocess.run(
        ["git", "-C", str(root), "archive", "--format=tar", f"--prefix={prefix}", "HEAD"],
        capture_output=True,
        check=False,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ValueError(f"git archive failed: {detail}. Run from a Git checkout.")
    return result.stdout


def write_archive(root: Path, version: str, folder: Path) -> Path:
    """Write the deterministic tar.gz of HEAD into an empty folder."""
    _require_empty_folder(folder)
    tar_bytes = _read_head_tar(root, version)
    output = folder / archive_name(version)
    with output.open("wb") as raw:
        # An empty filename keeps the output path out of the gzip header.
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=GZIP_LEVEL, mtime=GZIP_MTIME) as stream:
            stream.write(tar_bytes)
    return output


def find_asset_problems(folder: Path, version: str, require_bundles: bool = False) -> list[str]:
    """Return one line per missing expected file and per extra entry."""
    expected = {archive_name(version)}
    if require_bundles:
        expected.add(bundle_name(version))
    present = {entry.name for entry in folder.iterdir()} if folder.is_dir() else set()
    problems = [f"Missing {name}." for name in sorted(expected - present)]
    problems.extend(f"Unexpected {name}." for name in sorted(present - expected))
    return problems


def compute_file_sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of one file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(folder: Path) -> Path:
    """Write SHA256SUMS.txt for every other regular file in the folder."""
    output = folder / CHECKSUM_FILE
    files = sorted(path for path in folder.iterdir() if path.is_file() and path.name != CHECKSUM_FILE)
    lines = [f"{compute_file_sha256(path)}  {path.name}\n" for path in files]
    output.write_text("".join(lines), encoding="ascii")
    return output


def extract_changelog_section(changelog: str, version: str) -> str:
    """Return the body of one version's section without its heading."""
    headings = list(CHANGELOG_HEADING.finditer(changelog))
    for index, heading in enumerate(headings):
        if heading.group(1) != version:
            continue
        body_start = changelog.index("\n", heading.start()) + 1
        end = headings[index + 1].start() if index + 1 < len(headings) else len(changelog)
        return changelog[body_start:end].strip()
    raise ValueError(f"{CHANGELOG_FILE} holds no section for {version}. Add the entry first.")


def build_pin_block(sha: str) -> str:
    """Return the caller pin block for one full commit SHA."""
    if not COMMIT_SHA_PATTERN.fullmatch(sha):
        raise ValueError(f"{sha!r} is not a full lowercase commit SHA.")
    lines = [f"uses: {REPOSITORY}/.github/workflows/{workflow}@{sha}" for workflow in CALLER_WORKFLOWS]
    lines.append("with:")
    lines.append(f'  personas_ref: "{sha}"')
    return PIN_NOTES_HEADER + "\n".join(lines) + "\n```\n"


def build_notes(root: Path, version: str, sha: str) -> str:
    """Return the CHANGELOG section of one version followed by the pin block."""
    changelog = (root / CHANGELOG_FILE).read_text(encoding="utf-8")
    section = extract_changelog_section(changelog, version)
    return f"{section}\n\n{build_pin_block(sha)}"


def _report(problems: list[str]) -> int:
    """Print each problem and return the matching exit code."""
    for problem in problems:
        print(problem)
    return CHECK_FAILED if problems else 0


def _run(arguments: argparse.Namespace) -> int:
    """Run one parsed subcommand and return its exit code."""
    root = arguments.root
    if arguments.command == "check-tag":
        return _report(find_tag_problems(arguments.tag, root))
    if arguments.command == "archive":
        output = write_archive(root, require_version(arguments.version), arguments.folder)
        print(f"Wrote {output.name}.")
        return 0
    if arguments.command == "check-assets":
        version = require_version(arguments.version)
        return _report(find_asset_problems(arguments.folder, version, arguments.require_bundles))
    if arguments.command == "checksums":
        print(f"Wrote {write_checksums(arguments.folder).name}.")
        return 0
    notes = build_notes(root, require_version(arguments.version), arguments.sha)
    arguments.output.write_text(notes, encoding="utf-8")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Return the command line parser."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Repository root.")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-tag", help="Check a tag against CHANGELOG.md.")
    check.add_argument("tag")
    archive = commands.add_parser("archive", help="Write the tar.gz of HEAD.")
    archive.add_argument("version")
    archive.add_argument("folder", type=Path)
    assets = commands.add_parser("check-assets", help="Check the asset file names.")
    assets.add_argument("folder", type=Path)
    assets.add_argument("version")
    assets.add_argument("--require-bundles", action="store_true")
    sums = commands.add_parser("checksums", help="Write SHA256SUMS.txt for a folder.")
    sums.add_argument("folder", type=Path)
    notes = commands.add_parser("notes", help="Write the notes of one version.")
    notes.add_argument("version")
    notes.add_argument("sha")
    notes.add_argument("output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run one subcommand, and return its exit code."""
    arguments = _build_parser().parse_args(argv)
    try:
        return _run(arguments)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(f"error: {error}", file=sys.stderr)
        return CHECK_FAILED


if __name__ == "__main__":
    sys.exit(main())

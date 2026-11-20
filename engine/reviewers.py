"""Load and validate persona manifests under reviewers/<name>/reviewer.json.

The engine holds no persona-specific branch. Every persona difference lives
in its manifest, so this module is the single reader of that schema.
"""
import json
import string
from pathlib import Path

MANIFEST_NAME = "reviewer.json"
REVIEWERS_DIRECTORY = "reviewers"
# The scaffold for a new persona. The checker validates it. The persona list
# excludes it, so the engine skips it.
TEMPLATE_DIRECTORY = "_template"
MAX_NAME_LENGTH = 32
# Context output lands in an agent prompt. The cap keeps one mode well under
# the policy size budget a client loads beside it.
MAX_CONTEXT_BYTES = 32 * 1024
TOP_LEVEL_KEYS = frozenset({"persona", "function", "modes"})
# euler's envelope budget: a 976,000-token context minus the reply, the
# prompt, the chat template, and the retry note. A byte-level tokenizer emits
# at most one token per UTF-8 byte, so the byte count bounds the tokens.
ENVELOPE_BYTE_CEILING = 976_000 - 16_384 - 32_768 - 4_096 - 65_536
# Each chunk costs up to two model calls. The ceiling bounds one run's cost.
CAP_CEILINGS = {"max_chunks": 50, "max_envelope_bytes": ENVELOPE_BYTE_CEILING}
CAP_DEFAULTS = {"max_chunks": 20, "max_envelope_bytes": ENVELOPE_BYTE_CEILING}
# json_mode names the VERDICT_JSON mode value a persona prompt emits, for
# example "PR" in the foucault contract. Without it the engine skips the check.
MODE_KEYS = frozenset({"prompt", "review", "context", "default", "json_mode", *CAP_CEILINGS})
MODE_FLAGS = ("review", "context", "default")
NAME_CHARACTERS = frozenset(string.ascii_lowercase + string.digits + "-")


class ReviewerError(ValueError):
    """A persona request or manifest the engine refuses."""


def is_valid_name(name: str) -> bool:
    """Return whether a persona, function, or mode name is lowercase kebab case.

    A plain character scan avoids a regular expression with nested
    quantifiers.
    """
    if not name or len(name) > MAX_NAME_LENGTH:
        return False
    if not name[0].isascii() or not name[0].isalpha() or name.endswith("-"):
        return False
    if "--" in name:
        return False
    return all(character in NAME_CHARACTERS for character in name)


def reviewers_root(root: Path) -> Path:
    """Return the reviewers/ directory below a repository root."""
    return Path(root) / REVIEWERS_DIRECTORY


def list_personas(root: Path) -> list[str]:
    """Return runnable persona directory names, excluding the template."""
    directory = reviewers_root(root)
    if not directory.is_dir():
        return []
    return sorted(
        path.name for path in directory.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    )


def read_manifest(persona_dir: Path) -> dict:
    """Return the parsed manifest of one persona directory."""
    manifest_path = Path(persona_dir) / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ReviewerError(f"{persona_dir.name}: {MANIFEST_NAME} is missing")
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ReviewerError(
            f"{persona_dir.name}: {MANIFEST_NAME} is not valid JSON ({error})") from error
    if not isinstance(document, dict):
        raise ReviewerError(f"{persona_dir.name}: {MANIFEST_NAME} must hold a JSON object")
    return document


def prompt_path(persona_dir: Path, relative: object) -> Path:
    """Return a prompt path that stays inside the persona directory."""
    if not isinstance(relative, str) or not relative:
        raise ReviewerError("prompt must be a non-empty relative path")
    base = Path(persona_dir).resolve()
    candidate = (base / relative).resolve()
    if Path(relative).is_absolute() or not candidate.is_relative_to(base):
        raise ReviewerError(f"prompt '{relative}' escapes the persona directory")
    return candidate


def _is_cap_value(value: object, ceiling: int) -> bool:
    """Return whether a cap is an integer from 1 to its ceiling."""
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= ceiling


def resolve_caps(mode: dict, requested: dict | None = None) -> dict:
    """Return the effective caps for one mode and the names of clamped requests.

    A mode cap replaces the engine default. A caller request can lower a cap.
    A request above the cap keeps the cap and lands in the clamped list.
    """
    requested = requested or {}
    unknown = sorted(set(requested) - set(CAP_CEILINGS))
    if unknown:
        raise ReviewerError(f"unknown cap request {unknown}")
    caps = {"clamped": []}
    for name, ceiling in CAP_CEILINGS.items():
        limit = mode.get(name, CAP_DEFAULTS[name])
        request = requested.get(name)
        if request is None:
            caps[name] = limit
            continue
        if not _is_cap_value(request, ceiling):
            raise ReviewerError(f"cap request '{name}' must be an integer from 1 to {ceiling}")
        caps[name] = min(limit, request)
        if request > limit:
            caps["clamped"].append(name)
    return caps


def _unknown_keys(document: dict, allowed: frozenset, label: str) -> list[str]:
    """Return one finding per key outside the allowed set."""
    return [f"{label}: unknown key '{key}'" for key in sorted(set(document) - allowed)]


def _mode_findings(persona_dir: Path, name: str, mode: object) -> list[str]:
    """Return schema findings for one mode entry."""
    label = f"{persona_dir.name} mode '{name}'"
    if not is_valid_name(name):
        return [f"{persona_dir.name}: invalid mode name '{name}'"]
    if not isinstance(mode, dict):
        return [f"{label}: entry must be a JSON object"]
    findings = _unknown_keys(mode, MODE_KEYS, label)
    for flag in MODE_FLAGS:
        if flag in mode and not isinstance(mode[flag], bool):
            findings.append(f"{label}: '{flag}' must be true or false")
    for cap, ceiling in CAP_CEILINGS.items():
        if cap in mode and not _is_cap_value(mode[cap], ceiling):
            findings.append(f"{label}: '{cap}' must be an integer from 1 to {ceiling}")
    json_mode = mode.get("json_mode")
    if "json_mode" in mode and not (isinstance(json_mode, str) and json_mode.isascii()
                                    and json_mode.isprintable() and 0 < len(json_mode) <= MAX_NAME_LENGTH):
        findings.append(f"{label}: 'json_mode' must be printable ASCII of 1 to {MAX_NAME_LENGTH} characters")
    if not mode.get("review") and not mode.get("context"):
        findings.append(f"{label}: no delivery (set review or context to true)")
    try:
        path = prompt_path(persona_dir, mode.get("prompt"))
    except ReviewerError as error:
        return findings + [f"{label}: {error}"]
    if not path.is_file():
        findings.append(f"{label}: prompt '{mode.get('prompt')}' is missing")
    return findings


def _identity_findings(persona_dir: Path, document: dict) -> list[str]:
    """Return findings for the persona and function names."""
    name = persona_dir.name
    findings = []
    if name != TEMPLATE_DIRECTORY and not is_valid_name(name):
        findings.append(f"{name}: invalid persona name")
    if document.get("persona") != name:
        findings.append(f"{name}: persona '{document.get('persona')}' does not match directory")
    function = document.get("function")
    if not isinstance(function, str) or not is_valid_name(function):
        findings.append(f"{name}: invalid function name '{function}'")
    return findings


def validate_persona(persona_dir: Path) -> list[str]:
    """Return every schema finding for one persona directory."""
    persona_dir = Path(persona_dir)
    try:
        document = read_manifest(persona_dir)
    except ReviewerError as error:
        return [str(error)]
    findings = _unknown_keys(document, TOP_LEVEL_KEYS, persona_dir.name)
    findings += _identity_findings(persona_dir, document)
    modes = document.get("modes")
    if not isinstance(modes, dict) or not modes:
        return findings + [f"{persona_dir.name}: declares no modes"]
    for name, mode in modes.items():
        findings += _mode_findings(persona_dir, name, mode)
    defaults = [name for name, mode in modes.items()
                if isinstance(mode, dict) and mode.get("default") is True]
    if len(defaults) != 1:
        findings.append(f"{persona_dir.name}: needs exactly one default mode, found {len(defaults)}")
    return findings


def load_persona(root: Path, persona: str) -> tuple[Path, dict]:
    """Return the directory and validated manifest of a runnable persona."""
    if not is_valid_name(persona):
        raise ReviewerError(f"invalid persona name '{persona}'")
    if persona not in list_personas(root):
        raise ReviewerError(f"unknown persona '{persona}'")
    persona_dir = reviewers_root(root) / persona
    findings = validate_persona(persona_dir)
    if findings:
        raise ReviewerError("; ".join(findings))
    return persona_dir, read_manifest(persona_dir)


def default_mode(manifest: dict) -> str:
    """Return the single default mode of a validated manifest."""
    return next(name for name, mode in manifest["modes"].items() if mode.get("default"))


def resolve_review_modes(manifest: dict, requested: str) -> list[str]:
    """Return the review modes for a comma-separated request.

    An empty request selects the default mode. The order follows the request
    and repeats collapse to one entry.
    """
    names = [part.strip() for part in requested.split(",") if part.strip()]
    if not names:
        names = [default_mode(manifest)]
    resolved = []
    for name in names:
        mode = manifest["modes"].get(name)
        if mode is None:
            raise ReviewerError(f"unknown mode '{name}' for persona '{manifest['persona']}'")
        if not mode.get("review"):
            raise ReviewerError(f"mode '{name}' has no review delivery")
        if name not in resolved:
            resolved.append(name)
    return resolved

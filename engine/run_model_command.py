#!/usr/bin/env python3
"""Run the caller's model adapter command without shell interpretation.

Ported from `abuzucom/foucault` `ci/run_model_command.py`. The adapter
script lives in the caller workspace, which is the working directory of
this runner. The engine checkout holds no adapter.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

FORBIDDEN_SHELL_TOKENS = (";", "&", "|", ">", "<", "`", "$", "(", ")")
MAX_DIAGNOSTIC_CHARS = 2_000
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SENSITIVE_ASSIGNMENT = re.compile(r"(?i)(token|password|secret|authorization|api[_-]?key)(\s*[:=]\s*)\S+")
# The adapter contract: prompt and case files in, report on standard output.
# MODEL_PROVIDER and USAGE_FILE reach the engine adapter. Every other
# variable in the runner environment stays out of the adapter process.
FORWARDED_ENVIRONMENT = frozenset({
    "AUDIT_PROMPT_FILE",
    "CASE_TEXT_FILE",
    "MODEL_API_KEY",
    "MODEL_PROVIDER",
    "USAGE_FILE",
    "PATH",
    "HOME",
    "LANG",
    "SystemRoot",
    "TEMP",
    "TMP",
})
REJECTED_EXIT_CODE = 2


def parse_command(command: str, workspace: Path) -> list[str]:
    """Return the argument list for one Python script inside the workspace."""
    if not command or any(token in command for token in FORBIDDEN_SHELL_TOKENS):
        raise ValueError("model_call_command contains shell syntax")
    try:
        arguments = shlex.split(command, posix=True)
    except ValueError as error:
        raise ValueError("model_call_command has invalid quoting") from error
    if len(arguments) != 2 or arguments[0] not in {"python", "python3"}:
        raise ValueError("model_call_command must name one Python script")
    if "\\" in arguments[1]:
        raise ValueError("model_call_command must use a workspace-relative path")
    script_argument = Path(arguments[1])
    if script_argument.is_absolute():
        raise ValueError("model_call_command script must be relative")
    root = workspace.resolve()
    script = (root / script_argument).resolve()
    if script.suffix != ".py" or root not in script.parents:
        raise ValueError("model_call_command script must remain in the workspace")
    return [sys.executable, str(script)]


def sanitize_diagnostics(text: str) -> str:
    """Return bounded adapter diagnostics without credentials or control characters."""
    sanitized = CONTROL_CHARACTERS.sub("?", text)
    sanitized = SENSITIVE_ASSIGNMENT.sub(r"\1\2<redacted>", sanitized)
    return sanitized[:MAX_DIAGNOSTIC_CHARS]


def main() -> int:
    """Run the validated adapter and forward its output or sanitized diagnostics."""
    try:
        arguments = parse_command(os.environ.get("MODEL_CALL_COMMAND", ""), Path.cwd())
        adapter_environment = {
            name: value for name, value in os.environ.items() if name in FORWARDED_ENVIRONMENT
        }
        result = subprocess.run(arguments, check=False, shell=False, capture_output=True,
                                text=True, env=adapter_environment)
    except (OSError, ValueError) as error:
        print(f"model command rejected: {error}. Set model_call_command to "
              "'python <workspace-relative script>.py'.", file=sys.stderr)
        return REJECTED_EXIT_CODE
    if result.returncode:
        print("model command failed. Read the adapter diagnostics below.", file=sys.stderr)
        diagnostics = sanitize_diagnostics(result.stderr or "").strip()
        if diagnostics:
            print(diagnostics, file=sys.stderr)
        return result.returncode
    print(result.stdout, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Wrap a persona hook command in a bubblewrap sandbox on Linux.

The sandbox unshares every namespace, so the hook has no network and its own
PID namespace with a private /proc. It sees system paths, the Python
installation, the engine, and the persona read-only. Only the paths the
caller names as writable, an empty home and the head tree copy, accept
writes. The checkout, the runner home, and every other runner file stay
outside.

PERSONAS_REQUIRE_SANDBOX=1 makes a missing bubblewrap fail closed. CI sets
it. An empty value or 0 uses bubblewrap when present. Without it, the run
warns and starts the hook as a plain child process. off skips the sandbox
for plumbing tests. CI never sets off.
"""

from __future__ import annotations

import os
import shutil
import sys
import warnings
from pathlib import Path

REQUIRE_VARIABLE = "PERSONAS_REQUIRE_SANDBOX"
REQUIRE_VALUES = ("", "0", "1", "off")
# Merged-usr hosts make these links into /usr. Other hosts keep directories.
SYSTEM_LINK_PATHS = ("/bin", "/sbin", "/lib", "/lib64", "/lib32")
SYSTEM_READ_PATHS = ("/usr", "/etc")


class SandboxUnavailable(RuntimeError):
    """The run requires a sandbox that this host cannot provide."""


def bwrap_path() -> str | None:
    """Return the bubblewrap executable on Linux, or None."""
    if not sys.platform.startswith("linux"):
        return None
    return shutil.which("bwrap")


def _system_arguments() -> list[str]:
    """Return the read-only system binds and the merged-usr links."""
    arguments = []
    for path in SYSTEM_READ_PATHS:
        if Path(path).is_dir():
            arguments += ["--ro-bind", path, path]
    for path in SYSTEM_LINK_PATHS:
        if Path(path).is_symlink():
            arguments += ["--symlink", os.readlink(path), path]
        elif Path(path).is_dir():
            arguments += ["--ro-bind", path, path]
    return arguments


def interpreter() -> str:
    """Return the resolved Python interpreter path for a hook command.

    uv and the runner toolcache reach Python through symlinked directories.
    Python computes its prefix from the path it starts with, so a hook in
    the sandbox starts with the real path inside the bound installation.
    """
    return os.path.realpath(sys.executable)


def _python_paths() -> list[Path]:
    """Return the Python installation directories outside the system binds."""
    candidates = {Path(sys.base_prefix).resolve(), Path(sys.prefix).resolve(), Path(interpreter()).parent}
    system = [Path(path) for path in SYSTEM_READ_PATHS]
    return sorted(path for path in candidates if not any(path.is_relative_to(root) for root in system))


def sandbox_command(command: list[str], workdir: Path, read_only: list[Path], writable: list[Path]) -> list[str]:
    """Return the bubblewrap argument array that runs command in the sandbox."""
    arguments = [bwrap_path() or "bwrap", "--unshare-all", "--die-with-parent", "--new-session",
                 *_system_arguments(), "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    for path in [*_python_paths(), *read_only]:
        resolved = str(Path(path).resolve())
        arguments += ["--ro-bind", resolved, resolved]
    # Writable binds come after the /tmp tmpfs, so a temp directory stays visible.
    for path in [workdir, *writable]:
        resolved = str(Path(path).resolve())
        arguments += ["--bind", resolved, resolved]
    return [*arguments, "--chdir", str(Path(workdir).resolve()), "--", *command]


def wrap(command: list[str], workdir: Path, read_only: list[Path], writable: list[Path]) -> list[str]:
    """Return the sandboxed command, the plain command after a warning, or raise.

    PERSONAS_REQUIRE_SANDBOX accepts only an empty value, 0, 1, or off. Any
    other value fails closed, so a typo never disables the requirement.
    """
    required = os.environ.get(REQUIRE_VARIABLE, "")
    if required not in REQUIRE_VALUES:
        raise SandboxUnavailable(f"{REQUIRE_VARIABLE} must be 0, 1, or off, not {required!r}. Fix the variable.")
    if required == "off":
        return command
    if bwrap_path() is not None:
        return sandbox_command(command, workdir, read_only, writable)
    if required == "1":
        raise SandboxUnavailable("bubblewrap is not installed, and this run requires the hook sandbox. "
                                 "Install bubblewrap or unset PERSONAS_REQUIRE_SANDBOX.")
    warnings.warn("bubblewrap is unavailable. The persona hook runs without a sandbox.", RuntimeWarning,
                  stacklevel=2)
    return command

"""Test engine/sandbox.py: persona hooks run under bubblewrap on Linux.

The sandbox denies the network, hides the checkout and the runner home, and
leaves only the head tree copy and an empty home writable. CI sets
PERSONAS_REQUIRE_SANDBOX=1. A run then fails closed without bubblewrap.
"""

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}
HAS_BWRAP = sys.platform.startswith("linux") and shutil.which("bwrap") is not None


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sandbox = _load("sandbox")
run_review = _load("run_review")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=GIT_ENV
    ).stdout.strip()


class ModeTest(unittest.TestCase):
    """The sandbox is required unless PERSONAS_REQUIRE_SANDBOX opts out with 0 or off."""

    def setUp(self):
        self.saved_mode = os.environ.get("PERSONAS_REQUIRE_SANDBOX")
        self.saved_path = sandbox.BWRAP_PATH
        self.addCleanup(self.restore)
        self.missing = tempfile.TemporaryDirectory()
        self.addCleanup(self.missing.cleanup)

    def restore(self):
        sandbox.BWRAP_PATH = self.saved_path
        if self.saved_mode is None:
            os.environ.pop("PERSONAS_REQUIRE_SANDBOX", None)
        else:
            os.environ["PERSONAS_REQUIRE_SANDBOX"] = self.saved_mode

    def without_bwrap(self, mode: str | None) -> None:
        sandbox.BWRAP_PATH = str(Path(self.missing.name) / "bwrap")
        if mode is None:
            os.environ.pop("PERSONAS_REQUIRE_SANDBOX", None)
        else:
            os.environ["PERSONAS_REQUIRE_SANDBOX"] = mode

    def test_unknown_value_is_refused(self):
        os.environ["PERSONAS_REQUIRE_SANDBOX"] = "yes please"
        with self.assertRaisesRegex(sandbox.SandboxUnavailable, "PERSONAS_REQUIRE_SANDBOX"):
            sandbox.wrap(["true"], workdir=Path("/tmp"), read_only=[], writable=[])

    def test_default_without_tool_fails_closed(self):
        for mode in (None, "", "1"):
            with self.subTest(mode=mode):
                self.without_bwrap(mode)
                with self.assertRaisesRegex(sandbox.SandboxUnavailable, "bubblewrap"):
                    sandbox.wrap(["true"], workdir=Path("/tmp"), read_only=[], writable=[])

    def test_zero_without_tool_warns(self):
        self.without_bwrap("0")
        with self.assertWarnsRegex(RuntimeWarning, "without a sandbox"):
            command = sandbox.wrap(["true"], workdir=Path("/tmp"), read_only=[], writable=[])
        self.assertEqual(command, ["true"])

    def test_off_runs_plain_command(self):
        os.environ["PERSONAS_REQUIRE_SANDBOX"] = "off"
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            command = sandbox.wrap(["true"], workdir=Path("/tmp"), read_only=[], writable=[])
        self.assertEqual(command, ["true"])


@unittest.skipUnless(sys.platform.startswith("linux"), "the trust check reads POSIX ownership")
class TrustedPathTest(unittest.TestCase):
    """Only a root-owned regular file that no group or other user can write counts as bubblewrap."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.candidate = Path(self.temp.name) / "bwrap"
        self.candidate.write_text("#!/bin/sh\n", encoding="ascii")
        self.candidate.chmod(0o755)

    def test_path_search_is_never_used(self):
        self.assertTrue(sandbox.BWRAP_PATH.startswith("/"))
        self.assertIsNone(sandbox.trusted_bwrap(str(Path(self.temp.name) / "absent")))

    def test_writable_file_is_rejected(self):
        self.candidate.chmod(0o777)
        self.assertIsNone(sandbox.trusted_bwrap(str(self.candidate)))

    def test_symlink_is_rejected(self):
        link = Path(self.temp.name) / "link"
        link.symlink_to(self.candidate)
        self.assertIsNone(sandbox.trusted_bwrap(str(link)))

    def test_owner_must_be_root(self):
        if os.geteuid() == 0:
            os.chown(self.candidate, 65534, -1)
        self.assertIsNone(sandbox.trusted_bwrap(str(self.candidate)))


@unittest.skipUnless(HAS_BWRAP, "bubblewrap runs on Linux only")
class CommandTest(unittest.TestCase):
    """The bubblewrap command isolates everything and binds only what the hook needs."""

    def test_command_unshares_binds_listed_paths(self):
        with tempfile.TemporaryDirectory() as workdir:
            tree = Path(workdir) / "tree"
            tree.mkdir()
            command = sandbox.sandbox_command(
                ["python3", "x.py"], workdir=Path(workdir), read_only=[ENGINE_DIR], writable=[tree]
            )
        self.assertEqual(command[-3:], ["--", "python3", "x.py"])
        for flag in ("--unshare-all", "--die-with-parent", "--new-session"):
            self.assertIn(flag, command)
        pairs = list(zip(command, command[1:]))
        self.assertIn(("--ro-bind", str(ENGINE_DIR.resolve())), pairs)
        self.assertIn(("--bind", str(tree.resolve())), pairs)
        self.assertIn(("--chdir", str(Path(workdir).resolve())), pairs)
        self.assertNotIn(str(Path.home()), [value for flag, value in pairs if "bind" in flag])

    def test_etc_binds_runtime_files(self):
        with tempfile.TemporaryDirectory() as workdir:
            command = sandbox.sandbox_command(["true"], workdir=Path(workdir), read_only=[], writable=[])
        pairs = list(zip(command, command[1:]))
        self.assertNotIn(("--ro-bind", "/etc"), pairs)
        etc_sources = {value for flag, value in pairs if flag == "--ro-bind-try" and value.startswith("/etc")}
        self.assertEqual(etc_sources, set(sandbox.ETC_RUNTIME_FILES))

    def test_engine_interpreter_runs_sandbox(self):
        with tempfile.TemporaryDirectory() as workdir:
            command = sandbox.sandbox_command(
                [sandbox.interpreter(), "-c", "import sys"], workdir=Path(workdir), read_only=[], writable=[]
            )
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_python_via_symlink_runs(self):
        with tempfile.TemporaryDirectory() as workdir, tempfile.TemporaryDirectory() as outside:
            # The link sits outside every bind, like a uv or toolcache alias directory.
            link_dir = Path(outside) / "linked-python"
            link_dir.symlink_to(Path(os.path.realpath(sys.executable)).parent)
            linked = link_dir / Path(os.path.realpath(sys.executable)).name
            original = sandbox.sys.executable
            sandbox.sys.executable = str(linked)
            try:
                command = sandbox.sandbox_command(
                    [sandbox.interpreter(), "-c", "import sys"], workdir=Path(workdir), read_only=[], writable=[]
                )
            finally:
                sandbox.sys.executable = original
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)


# The hook probes each boundary and reports every escape as a reply problem.
PROBE_SOURCE = """import json
import os
import socket
from pathlib import Path

PROBES = json.loads({probes!r})


def case_context(head_dir, changed, patches, options):
    victim = Path(head_dir) / "delete-me.txt"
    if victim.exists():
        victim.unlink()
    return {{"context": {{}}, "unreviewed": []}}


def validate_reply(payload, response, envelope):
    escapes = []
    try:
        socket.create_connection(("127.0.0.1", PROBES["port"]), timeout=2).close()
        escapes.append("reached a host port")
    except OSError:
        pass
    for path in PROBES["hidden"]:
        if Path(path).exists():
            escapes.append(f"saw {{path}}")
    try:
        Path(PROBES["persona"], "written.txt").write_text("x")
        escapes.append("wrote into the persona directory")
    except OSError:
        pass
    return escapes
"""
ADAPTER_SOURCE = """import json, sys
payload = {"mode": "PR", "verdict": "APPROVE", "findings": []}
sys.stdout.write("Mode: PR\\nScope: the diff.\\nVERDICT: APPROVE\\nVERDICT_JSON: " + json.dumps(payload) + "\\n")
"""


@unittest.skipUnless(HAS_BWRAP, "bubblewrap runs on Linux only")
class BoundaryTest(unittest.TestCase):
    """A sandboxed hook reaches no host port, no checkout file, and no read-only path for writes."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.addCleanup(self.listener.close)
        self.root = base / "personas"
        self.persona_dir = self.root / "reviewers" / "euler"
        self.persona_dir.mkdir(parents=True)
        self.repo = base / "repo"
        self.repo.mkdir()
        secret = self.repo / "checkout-secret.txt"
        outside = base / "outside-secret.txt"
        outside.write_text("runner file\n", encoding="utf-8")
        probes = {
            "port": self.listener.getsockname()[1],
            "persona": str(self.persona_dir),
            "hidden": [str(secret), str(outside), "/etc/hostname"],
        }
        (self.persona_dir / "review_hooks.py").write_text(
            PROBE_SOURCE.format(probes=json.dumps(probes)), encoding="utf-8"
        )
        (self.persona_dir / "Q.md").write_text("Review.\n", encoding="ascii")
        manifest = {
            "persona": "euler",
            "function": "quality",
            "modes": {"quality": {"prompt": "Q.md", "review": True, "default": True, "json_mode": "PR"}},
        }
        (self.persona_dir / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
        _git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "keep.txt").write_text("base\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "base")
        self.base = _git(self.repo, "rev-parse", "HEAD")
        (self.repo / "app.py").write_text("value = 1\n", encoding="utf-8")
        (self.repo / "delete-me.txt").write_text("x\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "head")
        self.head = _git(self.repo, "rev-parse", "HEAD")
        secret.write_text("checkout secret\n", encoding="utf-8")
        (self.repo / "adapter").mkdir()
        (self.repo / "adapter" / "fake.py").write_text(ADAPTER_SOURCE, encoding="utf-8")
        saved = os.environ.get("PERSONAS_REQUIRE_SANDBOX")
        os.environ["PERSONAS_REQUIRE_SANDBOX"] = "1"
        self.addCleanup(self.restore_require, saved)

    @staticmethod
    def restore_require(saved):
        if saved is None:
            os.environ.pop("PERSONAS_REQUIRE_SANDBOX", None)
        else:
            os.environ["PERSONAS_REQUIRE_SANDBOX"] = saved

    def test_sandboxed_hooks_escape_nothing(self):
        result = run_review.run_mode(
            run_review.RunOptions(
                root=self.root,
                persona="euler",
                mode="quality",
                repo=self.repo,
                base=self.base,
                head=self.head,
                pr_number=1,
                out_dir=Path(self.temp.name) / "out",
                title="T",
                body="B",
                model_call_command="python adapter/fake.py",
            )
        )
        self.assertEqual(result["verdict"], "APPROVE")
        self.assertFalse((self.persona_dir / "written.txt").exists())


if __name__ == "__main__":
    unittest.main()

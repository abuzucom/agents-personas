"""Test that a persona hook cannot read the provider key from its parent.

On Linux a same-user process can read /proc/<pid>/environ of another
process. engine/run_review.py marks itself non-dumpable at startup, which
makes its environ unreadable to the hook child. The review step runs the
engine through exec, so no shell process keeps the key either.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
WORKFLOW_PATH = ENGINE_DIR.parent / ".github" / "workflows" / "review.yml"
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
}
SYNTHETIC_KEY = "synthetic-provider-key-for-exposure-test"
# The hook tries to read the environ of its parent, the engine process.
HOOKS_SOURCE = f'''import os
from pathlib import Path


def validate_reply(payload, response, envelope):
    try:
        parent = Path(f"/proc/{{os.getppid()}}/environ").read_bytes()
    except OSError:
        return []
    return ["the provider key leaked through /proc"] if b"{SYNTHETIC_KEY}" in parent else []
'''
ADAPTER_SOURCE = """import json, sys
payload = {"mode": "PR", "verdict": "APPROVE", "findings": []}
sys.stdout.write("Mode: PR\\nScope: the diff.\\nVERDICT: APPROVE\\nVERDICT_JSON: " + json.dumps(payload) + "\\n")
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env=GIT_ENV).stdout.strip()


class WorkflowExecTest(unittest.TestCase):
    """The review step replaces its shell with the engine."""

    def test_review_step_execs_the_engine(self):
        jobs = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"]
        for job in ("review", "fork-review"):
            step = next(item for item in jobs[job]["steps"] if item["name"] == "Run review")
            with self.subTest(job=job):
                self.assertIn('exec python3 .agents-personas/engine/run_review.py "${arguments[@]}"', step["run"])


@unittest.skipUnless(sys.platform.startswith("linux"), "only Linux exposes another process environ in /proc")
@unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads every /proc environ")
class ProcEnvironTest(unittest.TestCase):
    """A hook child cannot read MODEL_API_KEY from the engine process."""

    def test_hook_cannot_read_the_key_from_the_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)
            persona_dir = base_dir / "personas" / "reviewers" / "euler"
            persona_dir.mkdir(parents=True)
            (persona_dir / "Q.md").write_text("Review code quality.\n", encoding="ascii")
            (persona_dir / "review_hooks.py").write_text(HOOKS_SOURCE, encoding="utf-8")
            manifest = {"persona": "euler", "function": "quality", "modes": {"quality": {
                "prompt": "Q.md", "review": True, "default": True, "json_mode": "PR"}}}
            (persona_dir / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
            repo = base_dir / "repo"
            repo.mkdir()
            _git(repo, "init", "-q", "-b", "main")
            (repo / "keep.txt").write_text("base\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "base")
            base = _git(repo, "rev-parse", "HEAD")
            (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
            (repo / "adapter").mkdir()
            (repo / "adapter" / "fake.py").write_text(ADAPTER_SOURCE, encoding="utf-8")
            _git(repo, "add", "app.py")
            _git(repo, "commit", "-q", "-m", "head")
            head = _git(repo, "rev-parse", "HEAD")
            # Hosts without bubblewrap fall back to the plain child. CI sets 1 and keeps the sandbox required.
            environment = {**os.environ, "MODEL_API_KEY": SYNTHETIC_KEY,
                           "MODEL_CALL_COMMAND": "python adapter/fake.py",
                           "PERSONAS_REQUIRE_SANDBOX": os.environ.get("PERSONAS_REQUIRE_SANDBOX", "0")}
            completed = subprocess.run(
                [sys.executable, str(ENGINE_DIR / "run_review.py"), "--root", str(base_dir / "personas"),
                 "--persona", "euler", "--mode", "quality", "--repo", str(repo), "--base", base, "--head", head,
                 "--pr-number", "1", "--out-dir", str(base_dir / "out")],
                cwd=repo, env=environment, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("VERDICT: APPROVE", completed.stdout)


if __name__ == "__main__":
    unittest.main()

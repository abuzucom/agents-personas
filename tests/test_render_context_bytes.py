"""Test that engine/render_context.py emits the prompt bytes unchanged.

Context output feeds an agent prompt on every platform. Text-mode standard
output on Windows rewrites each newline. A CRLF prompt then gains doubled
carriage returns. These cases capture raw bytes.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RENDER_SCRIPT = Path(__file__).resolve().parent.parent / "engine" / "render_context.py"
MANIFEST = {
    "persona": "generay",
    "function": "time",
    "modes": {"sync": {"prompt": "SYNC.md", "review": True, "context": True, "default": True}},
}


class RenderContextBytesTest(unittest.TestCase):
    """Rendered output equals the prompt file byte for byte."""

    def render_bytes(self, prompt: bytes) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as directory:
            persona_dir = Path(directory) / "reviewers" / "generay"
            persona_dir.mkdir(parents=True)
            (persona_dir / "reviewer.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
            (persona_dir / "SYNC.md").write_bytes(prompt)
            return subprocess.run(
                [sys.executable, str(RENDER_SCRIPT), "--root", directory,
                 "--persona", "generay", "--mode", "sync"],
                capture_output=True, check=False)

    def test_lf_prompt_bytes_pass_through(self):
        prompt = b"# Sync\nRule one.\nRule two.\n"
        result = self.render_bytes(prompt)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, prompt)

    def test_crlf_prompt_bytes_pass_through(self):
        prompt = b"# Sync\r\nRule one.\r\n"
        result = self.render_bytes(prompt)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, prompt)


if __name__ == "__main__":
    unittest.main()

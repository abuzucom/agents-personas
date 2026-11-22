"""Test the hook-era injection corpus under engine/eval/injection/hooks/.

A persona hook can quote changed-file text, for example the euler regex
check. These cases prove that such quotes land in REVIEW_TARGET and never in
TRUSTED_CONTEXT, from the real euler prescan through the engine envelope.
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "engine"
HOOK_CORPUS_DIR = ENGINE_DIR / "eval" / "injection" / "hooks"
REQUIRED_KEYS = {"id", "vector", "description", "payload", "expect"}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


envelope = _load("envelope")
persona_hooks = _load("persona_hooks")
euler_hooks = persona_hooks.load_review_hooks(REPO_ROOT / "reviewers" / "euler")


def _cases() -> list[dict]:
    return [json.loads(path.read_text(encoding="ascii")) for path in sorted(HOOK_CORPUS_DIR.glob("*.json"))]


class HookCorpusStructureTest(unittest.TestCase):
    """Each hook case names the context vector, a payload, and the expected behavior."""

    def test_cases_exist_and_use_the_context_vector(self):
        cases = _cases()
        self.assertTrue(cases)
        for case in cases:
            with self.subTest(case=case.get("id")):
                self.assertEqual(set(case), REQUIRED_KEYS)
                self.assertEqual(case["vector"], "context")

    def test_case_ids_match_file_names(self):
        for path in sorted(HOOK_CORPUS_DIR.glob("*.json")):
            with self.subTest(path=path.name):
                self.assertEqual(json.loads(path.read_text(encoding="ascii"))["id"], path.stem)


class HookExcerptPlacementTest(unittest.TestCase):
    """The real euler prescan quotes the payload. The envelope keeps it untrusted."""

    def test_quoted_payload_stays_in_the_review_target(self):
        for case in _cases():
            with self.subTest(case=case["id"]), tempfile.TemporaryDirectory() as directory:
                tree = Path(directory)
                source = f"import re\nPATTERN = re.compile({case['payload']!r})\n"
                (tree / "app.py").write_text(source, encoding="utf-8")
                patch = "--- /dev/null\n+++ b/app.py\n@@ -0,0 +1,2 @@\n" + "".join(
                    f"+{line}\n" for line in source.splitlines())
                result = euler_hooks.case_context(tree, ["app.py"], {"app.py": patch}, {"exclude_paths": ""})
                quoted = [item for item in result["context"]["prescan"] if "SYSTEM:" in item["message"]]
                self.assertTrue(quoted, "the regex check no longer quotes the pattern, so the case tests nothing")
                document = json.loads(envelope.build_envelope(
                    "euler", "quality", {"app.py": patch}, "T", "B", {"pr_number": 1},
                    context=result["context"], changed_files=["app.py"], unreviewed=[]))
                self.assertNotIn("SYSTEM:", json.dumps(document["TRUSTED_CONTEXT"]))
                self.assertIn("SYSTEM:", json.dumps(document["REVIEW_TARGET"]["prescan"]))


if __name__ == "__main__":
    unittest.main()

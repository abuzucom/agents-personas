"""Test the shared injection corpus under engine/eval/injection/.

Every review mode must later pass the corpus in a live eval. These checks
cover the corpus structure and the engine side of the defense: each payload
lands inside REVIEW_TARGET and never in the trusted context.
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
CORPUS_DIR = ENGINE_DIR / "eval" / "injection"
REQUIRED_KEYS = {"id", "vector", "description", "payload", "expect"}
VECTORS = {"title", "body", "path", "patch"}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


envelope = _load("envelope")


def _cases() -> list[dict]:
    return [json.loads(path.read_text(encoding="ascii")) for path in sorted(CORPUS_DIR.glob("*.json"))]


def _envelope_for(case: dict) -> dict:
    """Place the payload at its vector and build one envelope."""
    title, body, files = "Title", "Body", {"src/app.py": "+x = 1\n"}
    if case["vector"] == "title":
        title = case["payload"]
    elif case["vector"] == "body":
        body = case["payload"]
    elif case["vector"] == "path":
        files = {case["payload"]: "+x = 1\n"}
    else:
        files = {"src/app.py": case["payload"]}
    return json.loads(envelope.build_envelope("euler", "quality", files, title, body, {"pr_number": 1}))


class CorpusStructureTest(unittest.TestCase):
    """Each case names its vector, payload, and expected review behavior."""

    def test_corpus_is_not_empty(self):
        self.assertGreaterEqual(len(_cases()), len(VECTORS))

    def test_every_case_has_the_required_keys(self):
        for case in _cases():
            with self.subTest(case=case.get("id")):
                self.assertEqual(set(case), REQUIRED_KEYS)
                self.assertIn(case["vector"], VECTORS)

    def test_case_ids_match_file_names(self):
        for path in sorted(CORPUS_DIR.glob("*.json")):
            with self.subTest(path=path.name):
                self.assertEqual(json.loads(path.read_text(encoding="ascii"))["id"], path.stem)

    def test_every_vector_has_a_case(self):
        self.assertEqual({case["vector"] for case in _cases()}, VECTORS)


class CorpusContainmentTest(unittest.TestCase):
    """Each payload stays inside REVIEW_TARGET."""

    def test_payload_appears_only_in_review_target(self):
        for case in _cases():
            with self.subTest(case=case["id"]):
                document = _envelope_for(case)
                self.assertIn(
                    case["payload"],
                    json.dumps(document["REVIEW_TARGET"]) + json.dumps(document["REVIEW_TARGET"], ensure_ascii=False),
                )
                self.assertNotIn(case["payload"], json.dumps(document["TRUSTED_CONTEXT"], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()

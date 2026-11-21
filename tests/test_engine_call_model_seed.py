"""Test the fixed sampling seed in engine/call_model.py.

Temperature 0 still lets a provider sample differently between runs. A
fixed seed narrows that spread where the provider API accepts one. The
Anthropic Messages API takes no seed, so its request carries none.
"""
import importlib.util
import json
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"


def _load():
    spec = importlib.util.spec_from_file_location("call_model", ENGINE_DIR / "call_model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


call_model = _load()


def _body(protocol: str) -> dict:
    """Return the JSON body of one request for the protocol."""
    profile = {"protocol": protocol, "endpoint": call_model.ENDPOINTS_BY_PROTOCOL[protocol], "model": "m",
               "name": protocol}
    request = call_model._build_request(profile, "system", "case", "synthetic-key")
    return json.loads(request.data.decode("utf-8"))


class SeedTest(unittest.TestCase):
    """Every protocol with a seed parameter sends the fixed seed."""

    def test_seed_is_a_fixed_non_negative_integer(self):
        self.assertIsInstance(call_model.REVIEW_SEED, int)
        self.assertGreaterEqual(call_model.REVIEW_SEED, 0)

    def test_ollama_sends_the_seed_in_options(self):
        self.assertEqual(_body("ollama")["options"]["seed"], call_model.REVIEW_SEED)

    def test_openai_compatible_sends_the_seed(self):
        self.assertEqual(_body("openai-compatible")["seed"], call_model.REVIEW_SEED)

    def test_google_sends_the_seed_in_the_generation_config(self):
        self.assertEqual(_body("google")["generationConfig"]["seed"], call_model.REVIEW_SEED)

    def test_anthropic_sends_no_seed(self):
        self.assertNotIn("seed", json.dumps(_body("anthropic")))

    def test_every_protocol_keeps_temperature_zero(self):
        bodies = {protocol: _body(protocol) for protocol in call_model.ALLOWED_PROTOCOLS}
        self.assertEqual(bodies["ollama"]["options"]["temperature"], 0)
        self.assertEqual(bodies["openai-compatible"]["temperature"], 0)
        self.assertEqual(bodies["anthropic"]["temperature"], 0)
        self.assertEqual(bodies["google"]["generationConfig"]["temperature"], 0)


if __name__ == "__main__":
    unittest.main()

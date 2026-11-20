"""Test the provider adapter in engine/call_model.py.

The routing and rejection cases carry over from the foucault adapter tests.
New cases cover usage reporting, provider selection by name, and the one
retry on a transient status. The tests replace only the network call and
the provider table. The adapter logic runs unchanged.
"""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
ACTIVE_BUDGET_TOKENS = 100
LARGE_BUDGET_TOKENS = 1000
OLLAMA_ENDPOINT = "https://ollama.com/api"
ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1"
OVERFLOW_BODY = b'{"error": "prompt is too long: 9000 tokens > 8000 maximum"}'
UNRELATED_BODY = b'{"error": "invalid value for field: temperature"}'
SERVICE_UNAVAILABLE = 503
BAD_REQUEST = 400
PAYLOAD_TOO_LARGE = 413


def _load():
    spec = importlib.util.spec_from_file_location("call_model", ENGINE_DIR / "call_model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


call_model = _load()


def _config(large: bool = True) -> dict:
    """Return a provider table with an optional large-input profile."""
    config = {
        "active_provider": "ollama",
        "providers": {
            "ollama": {"protocol": "ollama", "endpoint": OLLAMA_ENDPOINT,
                       "model": "review-model", "max_input_tokens": ACTIVE_BUDGET_TOKENS},
            "anthropic": {"protocol": "anthropic", "endpoint": ANTHROPIC_ENDPOINT,
                          "model": "claude-model"},
        },
    }
    if large:
        config["large_input_provider"] = "ollama-large"
        config["providers"]["ollama-large"] = {
            "protocol": "ollama", "endpoint": OLLAMA_ENDPOINT,
            "model": "large-model", "max_input_tokens": LARGE_BUDGET_TOKENS,
        }
    return config


def _http_error(code: int, body: bytes = b"") -> HTTPError:
    return HTTPError(OLLAMA_ENDPOINT, code, "rejected", {}, io.BytesIO(body))


class _FakeResponse:
    """Minimal urlopen response carrying one provider reply."""

    def __init__(self, text: str, document: dict | None = None):
        self.headers = {}
        body = document if document is not None else {
            "message": {"content": text}, "prompt_eval_count": 11, "eval_count": 7}
        self._raw = json.dumps(body).encode("utf-8")

    def read(self, _limit: int) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _call(responses: list, large: bool = True, models: list | None = None,
          environment: dict | None = None):
    """Run call_model_with_usage against scripted provider results."""
    sent = models if models is not None else []

    def fake_urlopen(request, timeout):
        del timeout
        sent.append(json.loads(request.data.decode("utf-8"))["model"])
        result = responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    variables = {"MODEL_API_KEY": "synthetic"}
    variables.update(environment or {})
    with patch.dict("os.environ", variables, clear=False), \
            patch.object(call_model, "_load_config", return_value=_config(large=large)), \
            patch.object(call_model, "urlopen", fake_urlopen), \
            patch.object(call_model.time, "sleep"):
        return call_model.call_model_with_usage("p", "PR", "c")


class ProfileSelectionTest(unittest.TestCase):
    """select_profile picks the smallest configured model that fits."""

    def _select(self, tokens: int, large: bool = True) -> dict:
        with patch.object(call_model, "_load_config", return_value=_config(large=large)):
            return call_model.select_profile(tokens)

    def test_input_within_active_budget_uses_active_provider(self):
        self.assertEqual(self._select(ACTIVE_BUDGET_TOKENS)["model"], "review-model")

    def test_input_over_active_budget_uses_large_provider(self):
        self.assertEqual(self._select(ACTIVE_BUDGET_TOKENS + 1)["model"], "large-model")

    def test_input_over_every_budget_is_capacity_error(self):
        with self.assertRaises(call_model.InputTooLargeError):
            self._select(LARGE_BUDGET_TOKENS + 1)

    def test_missing_large_provider_is_capacity_error(self):
        with self.assertRaises(call_model.InputTooLargeError):
            self._select(ACTIVE_BUDGET_TOKENS + 1, large=False)


class ProviderByNameTest(unittest.TestCase):
    """MODEL_PROVIDER selects a table entry by name."""

    def test_named_provider_replaces_the_active_one(self):
        document = {"content": [{"type": "text", "text": "named reply"}],
                    "usage": {"input_tokens": 5, "output_tokens": 2}}
        models: list = []
        text, usage = _call([_FakeResponse("", document)], models=models,
                            environment={"MODEL_PROVIDER": "anthropic"})
        self.assertEqual((text, models), ("named reply", ["claude-model"]))
        self.assertEqual(usage["provider"], "anthropic")

    def test_unknown_provider_name_is_rejected(self):
        with self.assertRaisesRegex(call_model.ProviderError, "not configured"):
            _call([_FakeResponse("unused")], environment={"MODEL_PROVIDER": "missing"})


class UsageTest(unittest.TestCase):
    """The adapter reports token usage for the check summary."""

    def test_ollama_usage_is_reported(self):
        text, usage = _call([_FakeResponse("reply")])
        self.assertEqual(text, "reply")
        self.assertEqual(usage, {"provider": "ollama", "model": "review-model",
                                 "input_tokens": 11, "output_tokens": 7})

    def test_missing_usage_fields_report_none(self):
        _text, usage = _call([_FakeResponse("", {"message": {"content": "reply"}})])
        self.assertIsNone(usage["input_tokens"])
        self.assertIsNone(usage["output_tokens"])

    def test_main_writes_usage_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "prompt.txt").write_text("p", encoding="utf-8")
            (root / "case.txt").write_text("c", encoding="utf-8")
            environment = {
                "AUDIT_PROMPT_FILE": str(root / "prompt.txt"),
                "CASE_TEXT_FILE": str(root / "case.txt"),
                "USAGE_FILE": str(root / "usage.json"),
                "MODEL_API_KEY": "synthetic",
            }
            with patch.dict("os.environ", environment), \
                    patch.object(call_model, "_load_config", return_value=_config()), \
                    patch.object(call_model, "urlopen", lambda request, timeout: _FakeResponse("r")), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                exit_code = call_model.main()
            usage = json.loads((root / "usage.json").read_text(encoding="utf-8"))
        self.assertEqual((exit_code, output.getvalue()), (0, "r"))
        self.assertEqual(usage["output_tokens"], 7)


class RetryTest(unittest.TestCase):
    """A transient status gets exactly one retry."""

    def test_one_transient_failure_then_success(self):
        models: list = []
        text, _usage = _call([_http_error(SERVICE_UNAVAILABLE), _FakeResponse("ok")], models=models)
        self.assertEqual((text, len(models)), ("ok", 2))

    def test_two_transient_failures_fail(self):
        with self.assertRaisesRegex(call_model.ProviderError, "after one retry"):
            _call([_http_error(SERVICE_UNAVAILABLE), _http_error(SERVICE_UNAVAILABLE)])


class HttpRejectionRoutingTest(unittest.TestCase):
    """Only a context rejection retries on the large-input model."""

    def test_overflow_body_retries_on_large_model(self):
        models: list = []
        text, _usage = _call([_http_error(BAD_REQUEST, OVERFLOW_BODY), _FakeResponse("large")],
                             models=models)
        self.assertEqual((text, models), ("large", ["review-model", "large-model"]))

    def test_unrelated_body_fails_without_reroute(self):
        models: list = []
        with self.assertRaises(call_model.ProviderError) as raised:
            _call([_http_error(BAD_REQUEST, UNRELATED_BODY)], models=models)
        self.assertNotIsInstance(raised.exception, call_model.InputTooLargeError)
        self.assertEqual(str(raised.exception), "provider request failed with HTTP 400")
        self.assertEqual(models, ["review-model"])

    def test_overflow_without_large_model_is_capacity_error(self):
        with self.assertRaises(call_model.InputTooLargeError):
            _call([_http_error(BAD_REQUEST, OVERFLOW_BODY)], large=False)

    def test_http_413_reroutes_without_body_evidence(self):
        text, _usage = _call([_http_error(PAYLOAD_TOO_LARGE), _FakeResponse("large")])
        self.assertEqual(text, "large")

    def test_rejection_message_omits_the_provider_body(self):
        with self.assertRaises(call_model.ProviderError) as raised:
            _call([_http_error(BAD_REQUEST, UNRELATED_BODY)])
        self.assertNotIn("temperature", str(raised.exception))


class ShippedTableTest(unittest.TestCase):
    """engine/model_providers.json loads and every entry validates."""

    def test_every_shipped_profile_validates(self):
        config = json.loads((ENGINE_DIR / "model_providers.json").read_text(encoding="utf-8"))
        for name in config["providers"]:
            with self.subTest(provider=name):
                self.assertEqual(call_model._load_profile(name)["name"], name)


if __name__ == "__main__":
    unittest.main()

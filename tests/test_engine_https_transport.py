"""Test the HTTPS-only provider transport in engine/call_model.py.

open_https sends one request over http.client. It refuses every scheme but
HTTPS, tunnels through HTTPS_PROXY the way urllib did, skips the proxy for
NO_PROXY hosts, and raises urllib HTTPError for a 4xx or 5xx status so the
retry and overflow rules keep working.
"""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"


def _load():
    spec = importlib.util.spec_from_file_location("call_model_transport", ENGINE_DIR / "call_model.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["call_model_transport"] = module
    spec.loader.exec_module(module)
    return module


call_model = _load()
PROXY_TARGET = ("api.example.test", 443)


class _FakeHTTPResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self.reason = "reason"
        self.headers = {"Content-Length": str(len(body))}
        self._body = body

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]


class _FakeConnection:
    """Record how open_https builds and uses one connection."""

    created: list = []

    def __init__(self, host, port=None, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.tunnel = None
        self.sent = None
        self.closed = False
        self.status = 200
        _FakeConnection.created.append(self)

    def set_tunnel(self, host, port=None, headers=None):
        self.tunnel = (host, port, headers)

    def request(self, method, target, body=None, headers=None):
        self.sent = (method, target, body, headers)

    def getresponse(self):
        return _FakeHTTPResponse(self.status, b'{"ok": true}')

    def close(self):
        self.closed = True


def _request(url: str = "https://api.example.test/v1/chat?x=1"):
    return call_model.ProviderRequest(url, b"{}", {"Content-Type": "application/json"}, "POST")


class OpenHttpsTest(unittest.TestCase):
    def setUp(self):
        _FakeConnection.created = []
        patcher = patch.object(call_model.http.client, "HTTPSConnection", _FakeConnection)
        patcher.start()
        self.addCleanup(patcher.stop)

    def open(self, environment: dict, request=None):
        with patch.dict("os.environ", environment, clear=True):
            with call_model.open_https(request or _request(), timeout=5) as response:
                return response.read(100)

    def test_direct_request_reaches_the_endpoint_host(self):
        self.assertEqual(self.open({}), b'{"ok": true}')
        connection = _FakeConnection.created[0]
        self.assertEqual((connection.host, connection.port, connection.tunnel), ("api.example.test", 443, None))
        self.assertEqual(connection.sent[:2], ("POST", "/v1/chat?x=1"))
        self.assertTrue(connection.closed)

    def test_https_proxy_tunnels_to_the_endpoint(self):
        self.open({"HTTPS_PROXY": "http://proxy.example.test:3128"})
        connection = _FakeConnection.created[0]
        self.assertEqual((connection.host, connection.port), ("proxy.example.test", 3128))
        self.assertEqual(connection.tunnel[:2], PROXY_TARGET)

    def test_proxy_credentials_become_a_proxy_authorization_header(self):
        self.open({"HTTPS_PROXY": "http://user:secret@proxy.example.test:3128"})
        headers = _FakeConnection.created[0].tunnel[2]
        self.assertEqual(headers, {"Proxy-Authorization": "Basic dXNlcjpzZWNyZXQ="})

    def test_no_proxy_host_connects_directly(self):
        self.open({"HTTPS_PROXY": "http://proxy.example.test:3128", "NO_PROXY": "api.example.test"})
        self.assertEqual(_FakeConnection.created[0].host, "api.example.test")

    def test_error_status_raises_http_error_with_a_readable_body(self):
        original = _FakeConnection.getresponse
        with patch.object(_FakeConnection, "getresponse", lambda self: _FakeHTTPResponse(413, b"too large")):
            with self.assertRaises(HTTPError) as caught:
                self.open({})
        self.assertIs(_FakeConnection.getresponse, original)
        self.assertEqual(caught.exception.code, 413)
        self.assertEqual(caught.exception.read(), b"too large")
        self.assertTrue(_FakeConnection.created[0].closed)

    def test_non_https_scheme_is_refused_before_any_connection(self):
        for url in ("http://api.example.test/v1", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(call_model.ProviderError):
                self.open({}, _request(url))
        self.assertEqual(_FakeConnection.created, [])


if __name__ == "__main__":
    unittest.main()

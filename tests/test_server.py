import json

import httpx
import pytest

from kev_mcp_server import server

Q = {"issue": {"type": "choice", "instructions": "Issue?", "criteria": {"billing": "Duplicate charge", "other": "Other"}}}
BASE_HTTP_CLIENT = httpx.Client


def test_evaluate_posts_fixed_model_and_returns_response(monkeypatch):
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(200, json={"model": "kev-latest", "answers": {"issue": "billing"}, "usage": {"input_tokens": 4, "output_tokens": 1}, "latency_ms": 8})

    monkeypatch.setattr(server.httpx, "Client", lambda **kwargs: BASE_HTTP_CLIENT(transport=httpx.MockTransport(handler), **kwargs))
    got = server.kev_evaluate("Customer was charged twice", Q)
    assert got["answers"]["issue"] == "billing"
    assert json.loads(seen["request"].content) == {"state": "Customer was charged twice", "model": "kev-latest", "questions": Q}


def test_permute_uses_api_envelope(monkeypatch):
    seen = {}

    def handler(request):
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"orders": []})

    monkeypatch.setattr(server.httpx, "Client", lambda **kwargs: BASE_HTTP_CLIENT(transport=httpx.MockTransport(handler), **kwargs))
    assert server.kev_permute("s", Q, "issue", 4, 7) == {"orders": []}
    assert seen["payload"] == {"request": {"state": "s", "model": "kev-latest", "questions": Q}, "question": "issue", "n_perm": 4, "seed": 7}


def test_separate_and_models_routes(monkeypatch):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"answers": {}, "models": []})

    monkeypatch.setattr(server.httpx, "Client", lambda **kwargs: BASE_HTTP_CLIENT(transport=httpx.MockTransport(handler), **kwargs))
    server.kev_separate("s", Q)
    server.kev_list_models()
    assert calls == [("POST", "/v1/systemone/separate"), ("GET", "/v1/models")]


def test_timeout_and_invalid_json_are_reported(monkeypatch):
    def timeout_client(**kwargs):
        class Client:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def request(self, *args, **kwargs): raise httpx.ReadTimeout("late")
        return Client()

    monkeypatch.setattr(server.httpx, "Client", timeout_client)
    with pytest.raises(RuntimeError, match="timed out"):
        server.kev_list_models()

    def bad_json_client(**kwargs):
        return BASE_HTTP_CLIENT(transport=httpx.MockTransport(lambda req: httpx.Response(200, text="not-json")), **kwargs)

    monkeypatch.setattr(server.httpx, "Client", bad_json_client)
    with pytest.raises(RuntimeError, match="invalid JSON"):
        server.kev_list_models()


def test_validation():
    with pytest.raises(ValueError, match="non-empty"):
        server.kev_evaluate("s", {})
    with pytest.raises(ValueError, match="exactly one"):
        server.kev_permute("s", {**Q, "other": Q["issue"]}, "issue")

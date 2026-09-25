import json

import httpx
import pytest

from kev_mcp_server import server

Q = {"issue": {"type": "choice", "instructions": "Issue?", "criteria": {"billing": "Duplicate charge", "other": "Other"}}}
ANSWERS = {"issue": {"type": "choice", "choice": "billing", "confidence": 0.6, "probabilities": {"billing": 0.8, "other": 0.2}}}
BASE_HTTP_CLIENT = httpx.Client


@pytest.fixture(autouse=True)
def fresh_client(monkeypatch):
    """Drop the shared client so each test builds one from its patched httpx.Client."""
    monkeypatch.setattr(server, "_client", None)
    monkeypatch.delenv("KEV_API_BASE_URL", raising=False)


def mock_client(monkeypatch, handler):
    monkeypatch.setattr(server.httpx, "Client", lambda **kwargs: BASE_HTTP_CLIENT(transport=httpx.MockTransport(handler), **kwargs))


def test_evaluate_posts_fixed_model_and_returns_response(monkeypatch):
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(200, json={"model": "kev-latest", "answers": ANSWERS, "usage": {"input_tokens": 4, "output_tokens": 1}, "latency_ms": 8})

    mock_client(monkeypatch, handler)
    got = server.kev_evaluate("Customer was charged twice", Q)
    assert got["answers"]["issue"]["choice"] == "billing"
    assert got["answers"]["issue"]["probabilities"]["billing"] == 0.8
    assert json.loads(seen["request"].content) == {"state": "Customer was charged twice", "model": "kev-latest", "questions": Q}


def test_structured_state_is_passed_through(monkeypatch):
    seen = {}
    state = {"customer": {"id": 42, "charges": [19.99, 19.99]}, "vip": True, "note": None}

    def handler(request):
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"answers": ANSWERS})

    mock_client(monkeypatch, handler)
    server.kev_evaluate(state, Q)
    assert seen["payload"]["state"] == state


def test_default_base_url_and_override(monkeypatch):
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(200, json={"models": []})

    mock_client(monkeypatch, handler)
    assert server.DEFAULT_BASE_URL == "http://127.0.0.1:8008"
    server.kev_list_models()
    monkeypatch.setenv("KEV_API_BASE_URL", "http://192.168.5.157:8008/")
    server.kev_list_models()
    assert urls == ["http://127.0.0.1:8008/v1/models", "http://192.168.5.157:8008/v1/models"]


def test_http_client_is_reused(monkeypatch):
    created = []

    def factory(**kwargs):
        created.append(kwargs)
        return BASE_HTTP_CLIENT(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"models": []})), **kwargs)

    monkeypatch.setattr(server.httpx, "Client", factory)
    server.kev_list_models()
    server.kev_list_models()
    assert len(created) == 1
    assert created[0]["timeout"] == server.REQUEST_TIMEOUT


def test_permute_uses_api_envelope(monkeypatch):
    seen = {}

    def handler(request):
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"orders": []})

    mock_client(monkeypatch, handler)
    assert server.kev_permute("s", Q, "issue", 4, 7) == {"orders": []}
    assert seen["payload"] == {"request": {"state": "s", "model": "kev-latest", "questions": Q}, "question": "issue", "n_perm": 4, "seed": 7}


def test_separate_and_models_routes(monkeypatch):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"answers": ANSWERS, "models": []})

    mock_client(monkeypatch, handler)
    server.kev_separate("s", Q)
    server.kev_list_models()
    assert calls == [("POST", "/v1/systemone/separate"), ("GET", "/v1/models")]


def test_timeout_and_invalid_json_are_reported(monkeypatch):
    def raise_timeout(request):
        raise httpx.ReadTimeout("late", request=request)

    mock_client(monkeypatch, raise_timeout)
    with pytest.raises(RuntimeError, match="timed out"):
        server.kev_list_models()

    monkeypatch.setattr(server, "_client", None)
    mock_client(monkeypatch, lambda req: httpx.Response(200, text="not-json"))
    with pytest.raises(RuntimeError, match="invalid JSON"):
        server.kev_list_models()


def test_connection_and_http_errors_are_reported(monkeypatch):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    mock_client(monkeypatch, refuse)
    with pytest.raises(RuntimeError, match="Could not reach Kev API"):
        server.kev_list_models()

    monkeypatch.setattr(server, "_client", None)
    mock_client(monkeypatch, lambda req: httpx.Response(503, text="busy"))
    with pytest.raises(RuntimeError, match="HTTP 503.*busy"):
        server.kev_list_models()


def test_validation():
    with pytest.raises(ValueError, match="non-empty"):
        server.kev_evaluate("s", {})
    with pytest.raises(ValueError, match="exactly one"):
        server.kev_permute("s", {**Q, "other": Q["issue"]}, "issue")


def test_transport_defaults_to_stdio():
    assert server._transport_config([], {}) == ("stdio", "127.0.0.1", 8765)


def test_transport_from_env():
    env = {"KEV_MCP_TRANSPORT": "streamable-http", "KEV_MCP_HOST": "0.0.0.0", "KEV_MCP_PORT": "9000"}
    assert server._transport_config([], env) == ("streamable-http", "0.0.0.0", 9000)


def test_transport_cli_overrides_env():
    env = {"KEV_MCP_TRANSPORT": "streamable-http", "KEV_MCP_PORT": "9000"}
    argv = ["--transport", "stdio", "--host", "::1", "--port", "7000"]
    assert server._transport_config(argv, env) == ("stdio", "::1", 7000)


@pytest.mark.parametrize("argv,env", [(["--transport", "sse"], {}), ([], {"KEV_MCP_TRANSPORT": "bogus"}), ([], {"KEV_MCP_PORT": "http"})])
def test_transport_rejects_invalid_values(argv, env):
    with pytest.raises(SystemExit):
        server._transport_config(argv, env)


@pytest.fixture
def http_env(monkeypatch):
    """Capture uvicorn.run instead of serving, and isolate FastMCP settings and auth env."""
    import uvicorn

    ran = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: ran.append((app, kwargs)))
    monkeypatch.setattr(server.mcp, "run", lambda transport: ran.append(("mcp.run", transport)))
    monkeypatch.setattr(server.mcp, "settings", server.mcp.settings.model_copy())
    for name in ("KEV_MCP_ALLOWED_HOSTS", "KEV_MCP_ALLOWED_ORIGINS", "KEV_MCP_AUTH_TOKEN", "KEV_MCP_AUTH_TOKEN_FILE"):
        monkeypatch.delenv(name, raising=False)
    return ran


def test_main_configures_http_transport(monkeypatch, http_env):
    monkeypatch.setenv("KEV_MCP_ALLOWED_HOSTS", "192.168.5.80:9001, kev-box:9001")
    monkeypatch.setenv("KEV_MCP_ALLOWED_ORIGINS", "http://localhost:3000")
    server.main(["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9001"])
    assert len(http_env) == 1
    app, kwargs = http_env[0]
    assert (kwargs["host"], kwargs["port"]) == ("0.0.0.0", 9001)
    assert not isinstance(app, server.BearerAuthMiddleware)
    assert (server.mcp.settings.host, server.mcp.settings.port) == ("0.0.0.0", 9001)
    security = server.mcp.settings.transport_security
    assert security is not None
    assert security.enable_dns_rebinding_protection is True
    assert security.allowed_hosts == ["192.168.5.80:9001", "kev-box:9001"]
    assert security.allowed_origins == ["http://localhost:3000"]


def test_non_loopback_http_requires_allowed_hosts(http_env):
    with pytest.raises(SystemExit, match="require KEV_MCP_ALLOWED_HOSTS"):
        server.main(["--transport", "streamable-http", "--host", "0.0.0.0"])
    assert http_env == []


def test_loopback_http_keeps_defaults_and_accepts_extra_hosts(monkeypatch, http_env):
    monkeypatch.setenv("KEV_MCP_ALLOWED_HOSTS", "kev.example.com")
    server.main(["--transport", "streamable-http"])
    security = server.mcp.settings.transport_security
    assert security.enable_dns_rebinding_protection is True
    assert security.allowed_hosts == server.LOOPBACK_ALLOWED_HOSTS + ["kev.example.com"]
    assert security.allowed_origins == server.LOOPBACK_ALLOWED_ORIGINS


def test_http_with_token_file_wraps_app(tmp_path, monkeypatch, http_env):
    token_file = tmp_path / "token"
    token_file.write_text("s3cret\n")
    monkeypatch.setenv("KEV_MCP_AUTH_TOKEN_FILE", str(token_file))
    server.main(["--transport", "streamable-http"])
    app, _ = http_env[0]
    assert isinstance(app, server.BearerAuthMiddleware)
    assert app._expected == b"s3cret"


def test_http_without_token_logs_warning(http_env, caplog):
    with caplog.at_level("WARNING", logger="kev_mcp_server"):
        server.main(["--transport", "streamable-http"])
    assert "WITHOUT authentication" in caplog.text


def test_stdio_ignores_auth(monkeypatch, http_env):
    monkeypatch.setenv("KEV_MCP_AUTH_TOKEN", "abc")
    server.main([])
    assert http_env == [("mcp.run", "stdio")]


def test_auth_token_sources(tmp_path):
    f = tmp_path / "t"
    f.write_text("  from-file \n")
    assert server._auth_token({}) is None
    assert server._auth_token({"KEV_MCP_AUTH_TOKEN_FILE": str(f)}) == "from-file"
    assert server._auth_token({"KEV_MCP_AUTH_TOKEN": "env", "KEV_MCP_AUTH_TOKEN_FILE": str(f)}) == "env"
    with pytest.raises(SystemExit):
        server._auth_token({"KEV_MCP_AUTH_TOKEN_FILE": str(tmp_path / "missing")})
    (tmp_path / "empty").write_text("\n")
    with pytest.raises(SystemExit):
        server._auth_token({"KEV_MCP_AUTH_TOKEN_FILE": str(tmp_path / "empty")})


async def _ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": b"ok"})


def _asgi_get(app, headers=None):
    import asyncio

    async def go():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
            return await client.post("/mcp", headers=headers or {}, content=b"{}")

    return asyncio.run(go())


def test_bearer_middleware_accepts_correct_token():
    resp = _asgi_get(server.BearerAuthMiddleware(_ok_app, "tok"), {"Authorization": "Bearer tok"})
    assert resp.status_code == 200 and resp.text == "ok"
    resp = _asgi_get(server.BearerAuthMiddleware(_ok_app, "tok"), {"Authorization": "bearer tok"})
    assert resp.status_code == 200


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic tok"}, {"Authorization": "Bearer"}, {"Authorization": "tok"}])
def test_bearer_middleware_rejects_missing_or_wrong_token(headers):
    resp = _asgi_get(server.BearerAuthMiddleware(_ok_app, "tok"), headers)
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"
    assert resp.headers["www-authenticate"].startswith("Bearer")


def test_no_token_passthrough():
    assert server.build_http_app(None).__class__.__name__ == "Starlette"
    assert _asgi_get(_ok_app).status_code == 200
    with pytest.raises(ValueError):
        server.BearerAuthMiddleware(_ok_app, "")


def test_bearer_middleware_passes_lifespan():
    import asyncio

    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(server.BearerAuthMiddleware(app, "tok")({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]

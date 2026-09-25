"""FastMCP adapter for the Kev pointer-head decision model API."""

from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

DEFAULT_BASE_URL = "http://127.0.0.1:8008"
REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=5.0)

TRANSPORTS = ("stdio", "streamable-http")
DEFAULT_TRANSPORT = "stdio"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
LOOPBACK_ALLOWED_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
LOOPBACK_ALLOWED_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]

logger = logging.getLogger("kev_mcp_server")

mcp = FastMCP("kev-mcp-server")

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    """Return the shared HTTP client, creating it on first use."""
    global _client
    if _client is None:
        _client = httpx.Client(timeout=REQUEST_TIMEOUT)
    return _client


def _request(method: str, path: str, *, payload: dict[str, Any] | None = None) -> Any:
    """Call Kev and return JSON, reporting transport/status/JSON failures clearly."""
    base_url = os.environ.get("KEV_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    try:
        response = _get_client().request(method, f"{base_url}{path}", json=payload)
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"Kev API request timed out at {path}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not reach Kev API at {path}: {exc}") from exc

    if response.is_error:
        body = response.text[:2000]
        raise RuntimeError(f"Kev API returned HTTP {response.status_code} for {path}: {body}")
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"Kev API returned invalid JSON for {path}") from exc


def _body(state: Any, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(questions, dict) or not questions:
        raise ValueError("questions must be a non-empty object")
    return {"state": state, "model": "kev-latest", "questions": questions}


@mcp.tool()
def kev_evaluate(state: Any, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Evaluate a decision state using Kev's pointer-head model; several questions may be packed into one call.

    `state` is any JSON value (string, object, list, number, bool, or null) describing the situation.
    `questions` maps answer keys to typed question objects:
    - choice: {type:'choice', instructions?, criteria:{name: description}} -> {choice, probabilities, confidence}
    - score: {type:'score', instructions?, criteria:[ordered labels, 1-255 items]}
      -> {score (probability-weighted expected value), legend, probabilities, confidence}
    - noul: {type:'noul', instructions?, criteria?} -> {noul: probability of yes, 0-1}
    `confidence` is a separate model signal, not the top probability (e.g. 0.27 when the top probability
    was 0.45), so base decision thresholds on `probabilities`.
    Returns the upstream model, answers (keyed like questions), usage, and latency_ms.
    """
    result = _request("POST", "/v1/systemone", payload=_body(state, questions))
    if not isinstance(result, dict):
        raise RuntimeError("Kev API returned a non-object response for evaluation")
    return result


@mcp.tool()
def kev_permute(
    state: Any,
    questions: dict[str, dict[str, Any]],
    question: str,
    n_perm: int = 6,
    seed: int = 0,
) -> dict[str, Any]:
    """Evaluate one Choice question under multiple option orders to check order sensitivity.

    `state` is any JSON value (string, object, list, number, bool, or null). `questions` must contain exactly
    one question of type 'choice' ({type:'choice', instructions?, criteria:{name: description}}) and
    `question` must be its key; n_perm is 1-64 and seed controls reproducibility.
    """
    if not 1 <= n_perm <= 64:
        raise ValueError("n_perm must be between 1 and 64")
    body = _body(state, questions)
    if question not in questions:
        raise ValueError("question must name a key in questions")
    if len(questions) != 1:
        raise ValueError("kev_permute requires exactly one question in questions")
    if questions[question].get("type") != "choice":
        raise ValueError("kev_permute supports Choice questions only")
    payload = {"request": body, "question": question, "n_perm": n_perm, "seed": seed}
    result = _request("POST", "/v1/systemone/permute", payload=payload)
    if not isinstance(result, dict):
        raise RuntimeError("Kev API returned a non-object response for permutation")
    return result


@mcp.tool()
def kev_separate(state: Any, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Evaluate each question independently against the same state for a packed-vs-separate comparison.

    `state` is any JSON value (string, object, list, number, bool, or null). `questions` uses the same
    format as kev_evaluate: choice {type:'choice', instructions?, criteria:{name: description}},
    score {type:'score', instructions?, criteria:[ordered labels, 1-255 items]}, or
    noul {type:'noul', instructions?, criteria?}. Base thresholds on `probabilities`, not `confidence`.
    """
    result = _request("POST", "/v1/systemone/separate", payload=_body(state, questions))
    if not isinstance(result, dict):
        raise RuntimeError("Kev API returned a non-object response for separate evaluation")
    return result


@mcp.tool()
def kev_list_models() -> dict[str, Any]:
    """List Kev models and metadata such as device, temperature, and prefix-cache statistics."""
    result = _request("GET", "/v1/models")
    if not isinstance(result, dict):
        raise RuntimeError("Kev API returned a non-object response for model listing")
    return result


def _transport_config(
    argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
) -> tuple[str, str, int]:
    """Resolve (transport, host, port) from CLI flags, falling back to KEV_MCP_* env vars, then defaults."""
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(prog="kev-mcp-server", description="Kev decision-model MCP server.")
    parser.add_argument(
        "--transport",
        choices=TRANSPORTS,
        default=env.get("KEV_MCP_TRANSPORT", DEFAULT_TRANSPORT),
        help="MCP transport (env KEV_MCP_TRANSPORT, default stdio)",
    )
    parser.add_argument(
        "--host",
        default=env.get("KEV_MCP_HOST", DEFAULT_HOST),
        help="bind host for streamable-http (env KEV_MCP_HOST, default 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=env.get("KEV_MCP_PORT", DEFAULT_PORT),
        help="bind port for streamable-http (env KEV_MCP_PORT, default 8765)",
    )
    args = parser.parse_args(argv)
    # argparse does not validate `choices` for env-supplied defaults.
    if args.transport not in TRANSPORTS:
        parser.error(f"unsupported transport {args.transport!r}; choose from {', '.join(TRANSPORTS)}")
    return args.transport, args.host, args.port


def _csv_env(name: str) -> list[str]:
    """Read a comma-separated environment variable as a trimmed list."""
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def _auth_token(env: Mapping[str, str] | None = None) -> str | None:
    """Return the bearer token from KEV_MCP_AUTH_TOKEN, else KEV_MCP_AUTH_TOKEN_FILE, else None."""
    env = os.environ if env is None else env
    token = env.get("KEV_MCP_AUTH_TOKEN", "").strip()
    if token:
        return token
    path = env.get("KEV_MCP_AUTH_TOKEN_FILE", "").strip()
    if not path:
        return None
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as fh:
            token = fh.read().strip()
    except OSError as exc:
        raise SystemExit(f"could not read KEV_MCP_AUTH_TOKEN_FILE {path!r}: {exc}") from exc
    if not token:
        raise SystemExit(f"KEV_MCP_AUTH_TOKEN_FILE {path!r} is empty")
    return token


class BearerAuthMiddleware:
    """Pure-ASGI middleware requiring `Authorization: Bearer <token>` on every HTTP request.

    Non-HTTP scopes (lifespan) pass straight through so the wrapped app's startup/shutdown still runs.
    """

    def __init__(self, app: Any, token: str) -> None:
        if not token:
            raise ValueError("token must be non-empty")
        self.app = app
        self._expected = token.encode("utf-8")

    def _authorized(self, scope: Mapping[str, Any]) -> bool:
        values = [
            value
            for name, value in scope.get("headers") or ()
            if name.lower() == b"authorization"
        ]
        # Reject duplicate credentials rather than letting an intermediary and
        # this middleware disagree about which Authorization value is effective.
        if len(values) != 1:
            return False
        scheme, separator, credentials = values[0].partition(b" ")
        if not separator or scheme.lower() != b"bearer":
            return False
        return hmac.compare_digest(credentials.strip(), self._expected)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or self._authorized(scope):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"error": "unauthorized", "error_description": "missing or invalid bearer token"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b'Bearer realm="kev-mcp-server"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _configure_transport_security(host: str) -> None:
    """Keep DNS-rebinding protection on; KEV_MCP_ALLOWED_HOSTS/ORIGINS extend loopback defaults."""
    allowed_hosts = _csv_env("KEV_MCP_ALLOWED_HOSTS")
    allowed_origins = _csv_env("KEV_MCP_ALLOWED_ORIGINS")
    if host in LOOPBACK_HOSTS:
        allowed_hosts = LOOPBACK_ALLOWED_HOSTS + allowed_hosts
        allowed_origins = LOOPBACK_ALLOWED_ORIGINS + allowed_origins
    elif not allowed_hosts:
        raise SystemExit(
            "non-loopback HTTP binds require KEV_MCP_ALLOWED_HOSTS (comma-separated Host header values)"
        )
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def build_http_app(token: str | None) -> Any:
    """Return the streamable-HTTP ASGI app, wrapped in bearer auth when a token is given."""
    app = mcp.streamable_http_app()
    return BearerAuthMiddleware(app, token) if token else app


def _run_http(host: str, port: int) -> None:
    """Serve streamable HTTP with uvicorn, mirroring FastMCP.run_streamable_http_async's config."""
    import uvicorn

    mcp.settings.host = host
    mcp.settings.port = port
    _configure_transport_security(host)
    token = _auth_token()
    if token:
        logger.info("bearer-token auth enabled for streamable-http")
    else:
        logger.warning(
            "streamable-http is running WITHOUT authentication; set KEV_MCP_AUTH_TOKEN or "
            "KEV_MCP_AUTH_TOKEN_FILE before exposing this server beyond localhost"
        )
    uvicorn.run(build_http_app(token), host=host, port=port, log_level=mcp.settings.log_level.lower())


def main(argv: Sequence[str] | None = None) -> None:
    """Run over stdio (default) or streamable HTTP when requested via --transport/KEV_MCP_TRANSPORT."""
    transport, host, port = _transport_config(argv)
    if transport == "streamable-http":
        logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
        _run_http(host, port)
        return
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()

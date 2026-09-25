"""FastMCP adapter for the Kev pointer-head decision model API."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_BASE_URL = "http://127.0.0.1:8008"
REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=5.0)

TRANSPORTS = ("stdio", "streamable-http")
DEFAULT_TRANSPORT = "stdio"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

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


def main(argv: Sequence[str] | None = None) -> None:
    """Run over stdio (default) or streamable HTTP when requested via --transport/KEV_MCP_TRANSPORT."""
    transport, host, port = _transport_config(argv)
    if transport == "streamable-http":
        mcp.settings.host = host
        mcp.settings.port = port
        if host not in LOOPBACK_HOSTS:
            # FastMCP enables localhost-only Host/Origin checks at construction time; drop them for LAN binds,
            # matching what FastMCP does when constructed with a non-loopback host.
            mcp.settings.transport_security = None
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()

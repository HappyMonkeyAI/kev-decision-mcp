"""FastMCP adapter for the Kev pointer-head decision model API."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_BASE_URL = "http://192.168.5.232:8008"
REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=5.0)

mcp = FastMCP("kev-mcp-server")


def _request(method: str, path: str, *, payload: dict[str, Any] | None = None) -> Any:
    """Call Kev and return JSON, reporting transport/status/JSON failures clearly."""
    base_url = os.environ.get("KEV_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.request(method, f"{base_url}{path}", json=payload)
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
def kev_evaluate(state: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Evaluate a decision state using Kev's pointer-head model. Questions map keys to typed question objects (usually {type:'choice', instructions:'...', criteria:{...}}). Returns the upstream model, answers, usage, and latency_ms."""
    result = _request("POST", "/v1/systemone", payload=_body(state, questions))
    if not isinstance(result, dict):
        raise RuntimeError("Kev API returned a non-object response for evaluation")
    return result


@mcp.tool()
def kev_permute(
    state: str,
    questions: dict[str, dict[str, Any]],
    question: str,
    n_perm: int = 6,
    seed: int = 0,
) -> dict[str, Any]:
    """Evaluate one Choice question under multiple option orders. `question` is the key of exactly one Choice in questions; n_perm is 1–64 and seed controls reproducibility."""
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
def kev_separate(state: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Evaluate each question independently against the same state for a packed-vs-separate comparison."""
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


def main() -> None:
    """Run over stdio for local MCP host integration."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

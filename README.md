# Kev MCP Server

A small stdio FastMCP adapter exposing the Kev pointer-head decision API at `http://127.0.0.1:8008` as four agent tools. The model identifier is intentionally fixed to `kev-latest` for decision calls; this is not a text-generation interface.

## Tools

- `kev_evaluate(state, questions)`: POST `/v1/systemone`; returns the upstream JSON object, including answers, usage, and `latency_ms`.
- `kev_permute(state, questions, question, n_perm=6, seed=0)`: POST `/v1/systemone/permute`. The API requires its documented wrapper `{request, question, n_perm, seed}`. Supply exactly one Choice question and its key as `question`; `n_perm` is 1–64.
- `kev_separate(state, questions)`: POST `/v1/systemone/separate`.
- `kev_list_models()`: GET `/v1/models`.

Question objects follow the Kev API schema, for example:

```json
{
  "issue": {
    "type": "choice",
    "instructions": "Issue?",
    "criteria": {
      "billing": "Duplicate charge",
      "other": "Other"
    }
  }
}
```

Transport timeouts, connection errors, HTTP errors, invalid JSON, and unexpected non-object API responses are surfaced as tool errors with concise context. Default HTTP timeout is 60 seconds (5 seconds to connect). Set `KEV_API_BASE_URL` to override the API origin; no credentials are embedded.

## Install and run

Requires Python 3.10+ and `uv` (or another PEP 517 package installer).

```bash
cd /home/stephen/projects/jev_mcp
uv sync
uv run kev-mcp-server
```

The server uses stdio transport and should be started by an MCP host, not run in a shell by itself. To use Python directly after installing dependencies:

```bash
uv run python -m kev_mcp_server.server
```

## Register with Hermes

Add this entry to `~/.hermes/config.yaml` under `mcp_servers` (merge it with existing entries):

```yaml
mcp_servers:
  kev:
    command: "/home/stephen/projects/jev_mcp/run-stdio.sh"
    timeout: 90
    connect_timeout: 30
```

The executable wrapper pins the stdio launch command and avoids argument-list serialization differences between Hermes versions. The server has already been registered in this Hermes profile using:

```bash
hermes config set mcp_servers.kev.command /home/stephen/projects/jev_mcp/run-stdio.sh
hermes mcp test kev
```

Other MCP hosts can launch the same stdio command directly. For Claude Desktop, use this server entry in its MCP config:

```json
{
  "mcpServers": {
    "kev": {
      "command": "uv",
      "args": ["--directory", "/home/stephen/projects/jev_mcp", "run", "kev-mcp-server"]
    }
  }
}
```

## Verification

```bash
uv run pytest
uv run python -m compileall -q src tests
uvx --from 'fastmcp<3' fastmcp inspect src/kev_mcp_server/server.py:mcp
hermes mcp test kev
```

Automated tests mock the HTTP API. A successful local test does not guarantee the upstream model is reachable; the server was also exercised through MCP against the live API for each tool during implementation.

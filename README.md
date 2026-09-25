# Kev MCP Server

A small FastMCP adapter (stdio by default, optional streamable HTTP) exposing the Kev jev model (https://github.com/jaredpalmer/kev) pointer-head decision API (default `http://127.0.0.1:8008`, configurable via `KEV_API_BASE_URL`) as four agent tools. The model identifier is intentionally fixed to `kev-latest` from https://github.com/jaredpalmer/kev for decision calls; this is not a text-generation interface.

## Tools

`state` may be any JSON value (string, object, list, number, boolean, or null); it is passed to Kev unchanged.

- `kev_evaluate(state, questions)`: POST `/v1/systemone`; returns the upstream JSON object, including answers, usage, and `latency_ms`.
- `kev_permute(state, questions, question, n_perm=6, seed=0)`: POST `/v1/systemone/permute`. The API requires its documented wrapper `{request, question, n_perm, seed}`. Supply exactly one Choice question and its key as `question`; `n_perm` is 1–64.
- `kev_separate(state, questions)`: POST `/v1/systemone/separate`.
- `kev_list_models()`: GET `/v1/models`.

## Question types

`questions` maps answer keys to typed question objects following the Kev API schema. Several questions can be packed into one `kev_evaluate` call; answers come back under the same keys.

| Type | Question object | Answer fields |
| --- | --- | --- |
| `choice` | `{type: "choice", instructions?, criteria: {name: description, ...}}` | `choice`, `probabilities` (per option), `confidence` |
| `score` | `{type: "score", instructions?, criteria: [ordered labels]}` (1–255 labels) | `score` (probability-weighted expected value), `legend`, `probabilities`, `confidence` |
| `noul` | `{type: "noul", instructions?, criteria?}` | `noul`: probability of "yes", 0–1 |

Example request `questions` and the corresponding answer:

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

```json
{
  "issue": {
    "type": "choice",
    "choice": "billing",
    "confidence": 0.6,
    "probabilities": {"billing": 0.8, "other": 0.2}
  }
}
```

`confidence` is a separate model signal, not the top probability (for example, a confidence of 0.27 has been observed when the top probability was 0.45). Base decision thresholds on `probabilities` (or `noul`/`score`), not on `confidence`.

Transport timeouts, connection errors, HTTP errors, invalid JSON, and unexpected non-object API responses are surfaced as tool errors with concise context. Default HTTP timeout is 60 seconds (5 seconds to connect); a single HTTP client is reused across calls. No credentials are embedded.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `KEV_API_BASE_URL` | `http://127.0.0.1:8008` | Kev API origin. **Set this when Kev runs on another machine**, e.g. `KEV_API_BASE_URL=http://192.168.5.157:8008`. |
| `KEV_MCP_TRANSPORT` | `stdio` | MCP transport: `stdio` or `streamable-http` (same as `--transport`). |
| `KEV_MCP_HOST` | `127.0.0.1` | Bind host for `streamable-http` (same as `--host`). |
| `KEV_MCP_PORT` | `8765` | Bind port for `streamable-http` (same as `--port`). |

Command-line flags take precedence over environment variables.

## Install and run

Requires Python 3.10+ and `uv` (or another PEP 517 package installer).

```bash
git clone https://github.com/HappyMonkeyAI/kev-decision-mcp.git
cd kev-decision-mcp
uv sync
uv run kev-mcp-server
```

By default the server uses stdio transport and should be started by an MCP host, not run in a shell by itself. To use Python directly after installing dependencies:

```bash
uv run python -m kev_mcp_server.server
```

If Kev is not on the same machine, point the adapter at it:

```bash
KEV_API_BASE_URL=http://192.168.5.157:8008 uv run kev-mcp-server
```

### Streamable HTTP (optional)

To serve MCP over the network instead of stdio:

```bash
uv run kev-mcp-server --transport streamable-http            # http://127.0.0.1:8765/mcp
KEV_MCP_TRANSPORT=streamable-http KEV_MCP_HOST=0.0.0.0 KEV_MCP_PORT=8765 uv run kev-mcp-server
```

The MCP endpoint is `/mcp`. **There is no authentication**: keep the default `127.0.0.1` bind unless you need remote clients, and only bind to `0.0.0.0` (or a LAN address) on a trusted network. When bound to a non-loopback host, FastMCP's localhost-only Host/Origin checks are disabled so LAN clients can connect.

## Register with Hermes

Add this entry to `~/.hermes/config.yaml` under `mcp_servers` (merge it with existing entries):

```yaml
mcp_servers:
  kev:
    command: "/home/user/kev-decision-mcp/run-stdio.sh"
    timeout: 90
    connect_timeout: 30
```

The executable wrapper pins the stdio launch command and avoids argument-list serialization differences between Hermes versions. The server has already been registered in this Hermes profile using:

```bash
hermes config set mcp_servers.kev.command /home/user/kev-decision-mcp/run-stdio.sh
hermes mcp test kev
```

Other MCP hosts can launch the same stdio command directly. For Claude Desktop, use this server entry in its MCP config:

```json
{
  "mcpServers": {
    "kev": {
      "command": "uv",
      "args": ["--directory", "/home/user/kev-decision-mcp", "run", "kev-mcp-server"]
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

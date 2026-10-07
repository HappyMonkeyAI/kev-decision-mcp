# Kev MCP Server

A small FastMCP adapter (stdio by default, optional streamable HTTP) exposing the Kev jev model (https://github.com/jaredpalmer/kev) pointer-head decision API (default `http://127.0.0.1:8008`, configurable via `KEV_API_BASE_URL`) as agent tools. The model identifier is intentionally fixed to `kev-latest` from https://github.com/jaredpalmer/kev for decision calls; this is not a text-generation interface.

## Tools

`state` may be any JSON value (string, object, list, number, boolean, or null); it is passed to Kev unchanged.

- `kev_evaluate(state, questions)`: POST `/v1/systemone`; returns the upstream JSON object, including answers, usage, and `latency_ms`.
- `kev_permute(state, questions, question, n_perm=6, seed=0)`: POST `/v1/systemone/permute`. The API requires its documented wrapper `{request, question, n_perm, seed}`. Supply exactly one Choice question and its key as `question`; `n_perm` is 1–64.
- `kev_separate(state, questions)`: POST `/v1/systemone/separate`.
- `kev_list_models()`: GET `/v1/models`.
- `kev_select_tool(state, tools)`: suggest a tool in shadow mode, returning probabilities without executing anything or generating arguments.
- `kev_custom_decision(task, state, options)`: evaluate one bounded, agent-defined choice schema with a reserved insufficient-information option. The schema applies to that call only.

### Shadow tool selection

Supply the user request, relevant prior context, and only the tools actually available
to the calling agent. Each tool needs a description; an optional `parameters` object
can contain its argument schema. The reserved option `__no_tool__` is added automatically.

```json
{
  "state": {
    "user_request": "Find where this project reads its API key",
    "context": "The current repository is available locally"
  },
  "tools": {
    "search_files": {"description": "Search text in local project files"},
    "web_search": {"description": "Search the web for external information"}
  }
}
```

The result contains `mode: "shadow"`, `suggested_tool` (a supplied tool name or
`null`), `executed: false`, `probabilities`, `top_probability`, and upstream model,
latency and usage metadata. No probability threshold or automatic fallback is applied.
The calling agent keeps its own decision and validates permissions and arguments.
A suggestion is not evidence that an action is authorised or that all arguments
are present. Upstream errors remain tool errors; the caller should continue its
normal decision process when Kev is unavailable.

For a trial, compare the suggestion with the agent's independently selected next
tool before changing its behaviour. Record agreement, whether the agent's choice
was correct after review, added latency, and the full model revision from
`kev_list_models()`. The adapter does not save requests or decisions to disk.
Tool names must be non-empty and cannot be `__no_tool__`; supply 1–254 tools.
The helper's paired ToolSelect pilot scored 518/552 (93.84%), versus 534/552
(96.74%) for the original prompt. It abstained on 21 tool-labelled cases. That
corpus does not test correct abstention, and the public training data does not
establish production reliability. Keep suggestions advisory.

To repeat the paired comparison against a running Kev server:

```bash
uv run python scripts/evaluate-shadow.py /path/to/toolselect.jsonl \
  --url http://127.0.0.1:8008 --output /path/to/benchmark-results-shadow-paired.json
```

The runner alternates baseline/helper order, records source/data fingerprints,
and reports failures explicitly. Set `KEV_API_KEY` if required by the API.

### Custom decision schema

Use `kev_custom_decision` when no focused tool fits. Supply a short task statement,
the case state, and 2–8 option IDs with concise meanings. The server adds the
reserved `__insufficient_information__` option, bounds the combined JSON input to
64 KiB, validates the returned option and full probability distribution, and
returns no free-form rationale or action. An abstention or a dominant upstream
rejection yields `selected_option: null`; inspect `abstained` and the probability
metadata. Results are advisory and uncalibrated. The per-call schema does not
change MCP tool registration or override the focused billing/trading tools.
See [docs/CUSTOM-DECISIONS.md](docs/CUSTOM-DECISIONS.md) for an example and limits.

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
| `KEV_API_BASE_URL` | `http://127.0.0.1:8008` | Kev API origin. Set this to the model API address when Kev runs on another machine. |
| `KEV_API_KEY` | unset | Bearer key sent to the upstream Kev API. Match the key configured in Kev; separate from `KEV_MCP_AUTH_TOKEN`, which protects incoming MCP requests. |
| `KEV_MCP_TRANSPORT` | `stdio` | MCP transport: `stdio` or `streamable-http` (same as `--transport`). |
| `KEV_MCP_HOST` | `127.0.0.1` | Bind host for `streamable-http` (same as `--host`). |
| `KEV_MCP_PORT` | `8765` | Bind port for `streamable-http` (same as `--port`). |
| `KEV_MCP_AUTH_TOKEN` | unset | Optional bearer token for `streamable-http`. When set, every HTTP request must send `Authorization: Bearer <token>`; others get `401` JSON. Ignored for stdio. |
| `KEV_MCP_AUTH_TOKEN_FILE` | unset | Path to a file containing the bearer token (whitespace trimmed). Used when `KEV_MCP_AUTH_TOKEN` is unset. |
| `KEV_MCP_ALLOWED_HOSTS` | unset | Comma-separated extra `Host` header values accepted by DNS-rebinding protection. Required for non-loopback binds; on loopback binds it extends the default `127.0.0.1:*`, `localhost:*`, `[::1]:*`. |
| `KEV_MCP_ALLOWED_ORIGINS` | unset | Comma-separated extra `Origin` values accepted (browser clients only). |

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
KEV_API_BASE_URL=http://kev-host.example:8008 uv run kev-mcp-server
```

### Streamable HTTP (optional)

To serve MCP over the network instead of stdio:

```bash
uv run kev-mcp-server --transport streamable-http            # http://127.0.0.1:8765/mcp
KEV_MCP_TRANSPORT=streamable-http \
KEV_MCP_HOST=0.0.0.0 \
KEV_MCP_PORT=8765 \
KEV_MCP_ALLOWED_HOSTS=kev-host.example:8765 \
uv run kev-mcp-server
```

The MCP endpoint is `/mcp`. Authentication is **off unless `KEV_MCP_AUTH_TOKEN` or `KEV_MCP_AUTH_TOKEN_FILE` is set** (the server logs a warning when HTTP runs without a token). With a token, every request must carry `Authorization: Bearer <token>` (compared in constant time); anything else gets `401` with a JSON body. Keep the default `127.0.0.1` bind unless you need remote clients, and only bind to `0.0.0.0` (or a LAN address) on a trusted network. Non-loopback binds require `KEV_MCP_ALLOWED_HOSTS`, a comma-separated list of exact `Host` header values accepted by FastMCP (for example, `kev-host.example:8765`). Replace the example hostname with the address clients use. Host and Origin validation remains enabled to protect against DNS rebinding; set the optional comma-separated `KEV_MCP_ALLOWED_ORIGINS` when browser clients need specific origins. Requests without an `Origin` header are allowed by FastMCP.

### Sharing over a Cloudflare quick tunnel

A [Cloudflare quick tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) gives the local HTTP server a public `https://<random>.trycloudflare.com` URL without opening any ports. Always set a token first, and keep the server bound to loopback:

```bash
mkdir -p ~/.config/kev-mcp
python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > ~/.config/kev-mcp/token
chmod 600 ~/.config/kev-mcp/token

KEV_MCP_TRANSPORT=streamable-http \
KEV_MCP_HOST=127.0.0.1 \
KEV_MCP_PORT=8765 \
KEV_MCP_AUTH_TOKEN_FILE=~/.config/kev-mcp/token \
uv run kev-mcp-server

# in another shell
cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8765 --http-host-header 127.0.0.1:8765
```

cloudflared prints the public hostname; the MCP URL is `https://<name>.trycloudflare.com/mcp`. Clients must send `Authorization: Bearer <token>`.

**Why `--http-host-header`:** cloudflared forwards the public `Host` header (`<name>.trycloudflare.com`) by default, and FastMCP's DNS-rebinding protection on a loopback bind only accepts `127.0.0.1:*`, `localhost:*` and `[::1]:*`, so requests would fail with `421 Invalid Host header`. Rewriting the Host header to `127.0.0.1:8765` keeps protection on without having to reconfigure the server each time a quick tunnel gets a new random hostname. (Alternatively, add the hostname to `KEV_MCP_ALLOWED_HOSTS`, which extends the loopback defaults, e.g. for a named tunnel with a stable hostname.) Browser-based clients that send an `Origin` header also need that origin in `KEV_MCP_ALLOWED_ORIGINS`.

Quick tunnels are intended for testing: the hostname changes whenever cloudflared restarts and there is no uptime guarantee. The bearer token is the only access control, so treat it like a password and rotate it (rewrite the file and restart the server) if it leaks.

## Register with Hermes

Add this entry to `~/.hermes/config.yaml` under `mcp_servers` (merge it with existing entries):

```yaml
mcp_servers:
  kev:
    command: "/home/user/kev-decision-mcp/run-stdio.sh"
    timeout: 90
    connect_timeout: 30
```

The executable wrapper pins the stdio launch command and avoids argument-list serialization differences between Hermes versions. Register the server in a Hermes profile with:

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

### Experimental crypto second opinion

An optional CPU Gutsy comparison backend runs separately on MCP port 8766;
the existing Kev endpoint remains on 8765. See [deployment and rejection semantics](docs/GUTSY-COMPARISON.md)
and [the paired Project23 results](benchmarks/GUTSY-RESULTS.md).

`kev_review_trade` reviews caller-supplied timestamped market context, a proposed
trade and explicit risk constraints in paper-advisory mode. It can return
supports_proposal, concerns or insufficient_information; it never places orders
or grants execution permission. See [the contract and label-review procedure](docs/TRADE-ADVISORY.md).
The previous two-choice Project23 benchmark does not validate this new prompt.

```bash
uv run pytest
uv run python -m compileall -q src tests
uvx --from 'fastmcp<3' fastmcp inspect src/kev_mcp_server/server.py:mcp
hermes mcp test kev
```

Automated tests mock the HTTP API. A successful local test does not guarantee the upstream model is reachable; the server was also exercised through MCP against the live API for each tool during implementation.

# Local advisory server on 192.168.5.157

Docker Desktop runs two services under the kev-advisory project:
Kev 4B (the cached pinned checkpoint) and the MCP adapter.
The model API publishes localhost:8008; clients use the MCP endpoint
http://192.168.5.157:8765/mcp. The adapter calls the model on the private Docker
network. The previous Kev 0.8B benchmark on .232 is a separate deployment.

Installation checked on 2026-10-04: both containers running, model healthy on
CUDA, LAN-address authentication rejection (401), authenticated MCP discovery,
missing/stale-context checks and a synthetic live review passed. Kev returned
insufficient_information for the synthetic fixture (0.6518, 190 ms warm model
latency). The full unit suite passed: 86 tests. Client access from another LAN
computer and the intended ChatGPT session are not yet verified. The first
verification client's shutdown hung; a fresh full HTTP MCP smoke test completed
successfully and only the old verification client was stopped.

## Start, stop and copy

Create .env from .env.example and set KEV_API_KEY to a random secret for the
model. KEV_MCP_AUTH_TOKEN is optional: blank disables MCP authentication.
On 2026-10-04, at the user's request, the local MCP token was cleared for LAN
use; the model API key remains enabled. A nonempty MCP token enables bearer
authentication. Never paste configured secrets into chat or commit them.

Run from this folder:

```powershell
docker compose -f compose.yaml -f compose.model.yaml up -d --build
docker compose -f compose.yaml -f compose.model.yaml ps
docker compose -f compose.yaml -f compose.model.yaml stop
```

The combined setup uses the existing kev-server:local image and external cache
volume docker_kev-hf-cache. Copying this folder alone does not copy that image or
cache to a different computer. Build the model image from kev-docker first and
configure an existing cache volume, or deliberately enable downloads with
HF_HUB_OFFLINE=0. Keep offline mode when using this machine's cached checkpoint.
Copying the adapter folder to another directory on the same computer reuses
the Docker image/cache, but needs its own private .env. The fixed project name
targets the same Compose services; stop the previous instance before relocating.
Do not include benchmarks/private, .venv or credentials in a shared copy.

The adapter-only command `docker compose up -d --build` can instead use
KEV_API_BASE_URL to point at an existing model API. Both modes require explicit
model authentication; MCP authentication is optional. Docker build context includes source/lockfiles only,
not .env or private datasets. The adapter uses a nonroot user and read-only root.

## Client configuration

For a client with LAN-capable streamable HTTP MCP support, configure the URL
above without an Authorization header when the MCP token is blank. If a token
is configured, supply Authorization: Bearer <KEV_MCP_AUTH_TOKEN> through secure
credential settings. Verify discovery before instructing it to call kev_review_trade.
An instruction in chat alone does not create an MCP connection. Availability
of LAN MCP connections in the intended ChatGPT desktop session has not been
verified; a remote connector may need an HTTPS endpoint accessible to it.
No public tunnel or firewall changes are made by this setup.

For a local stdio-capable host on this same computer, a copied source checkout
can launch `uv run kev-mcp-server` with KEV_API_BASE_URL=http://127.0.0.1:8008
and the matching KEV_API_KEY in its launch environment. That starts its own
adapter process rather than connecting to the Docker MCP HTTP endpoint.

Read TRADE-ADVISORY.md before paper tests. Responses are second opinions,
probabilities are uncalibrated, and no exchange connection or orders exist.

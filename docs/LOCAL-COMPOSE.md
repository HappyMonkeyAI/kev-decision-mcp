# Local Docker Compose deployment

This repository can run the MCP adapter beside an existing Kev model API, or
combine the adapter with the optional model and Gutsy Compose files. The adapter
connects to the model over the Docker network when both are in Compose, or to an
address configured with `KEV_API_BASE_URL` when the model runs elsewhere.

## Start and stop

Create a private `.env` from `.env.example` and configure the upstream model
credentials. `KEV_MCP_AUTH_TOKEN` is optional for trusted local use; set a strong
token whenever clients connect over a network you do not fully control. Never
commit `.env` or paste configured secrets into shared logs.

Start the adapter-only deployment with:

```sh
docker compose up -d --build
docker compose ps
docker compose stop
```

For a model deployment defined by this repository, follow the model-specific
instructions and combine its Compose file with `compose.yaml`. For the optional
Gutsy CPU backend, see [Gutsy comparison deployment](GUTSY-COMPARISON.md).

The adapter-only deployment expects an existing model API. If that API runs on
the host, set `KEV_API_BASE_URL` to a host address reachable from the container
(on Docker Desktop, `host.docker.internal` is commonly available). If it runs in
another container, use the Compose service name and internal port. The API key
must be configured privately and match the model service.

## Network access

The default MCP bind is loopback. To allow remote clients, set
`KEV_MCP_BIND_HOST=0.0.0.0` and explicitly set
`KEV_MCP_ALLOWED_HOSTS` to the exact `host:port` values clients use. Add a
bearer token for network clients and restrict access with the host firewall.
Do not use a wildcard to bypass Host validation. The container's MCP endpoint is
`/mcp`.

For example, with a private DNS entry `kev-host.example`:

```dotenv
KEV_MCP_BIND_HOST=0.0.0.0
KEV_MCP_ALLOWED_HOSTS=kev-host.example:8765
KEV_MCP_AUTH_TOKEN=replace-with-a-private-random-token
```

Copying this folder to another computer does not copy Docker images, model
caches, or private configuration. Build or pull the required image and provide
that host's own `.env`. Avoid sharing benchmark outputs if they contain private
data.

## Client configuration

Configure an MCP client to use the reachable `http://<host>:8765/mcp` endpoint.
If a token is set, supply it through the client's secure credential settings as
`Authorization: Bearer <token>`. Confirm MCP discovery before asking the client
to review decisions. A prompt alone does not create a connection.

For local stdio clients, install the project and launch `uv run kev-mcp-server`
with the model URL and key available in the process environment. This starts a
local adapter process rather than connecting to the Docker MCP endpoint.

Read [trade advisory limitations](../TRADE-ADVISORY.md) before paper testing.
Responses are second opinions; probabilities are uncalibrated, and the project
does not connect to exchanges or place orders.

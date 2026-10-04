FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM python:3.13-slim@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
USER 10001:10001
EXPOSE 8765
CMD ["kev-mcp-server", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8765"]

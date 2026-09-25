#!/bin/sh
SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
exec uv run --directory "$SCRIPT_DIR" kev-mcp-server

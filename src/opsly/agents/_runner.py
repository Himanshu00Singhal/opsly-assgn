"""Run MCP servers with streamable HTTP."""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from opsly.shared.logging import configure_logging


def run_mcp_server(server: MCPServer, *, default_port: int) -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", str(default_port)))
    server.run(
        transport="streamable-http",
        host=host,
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
    )

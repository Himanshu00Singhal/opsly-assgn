"""Code Analyst MCP server."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from opsly.agents._runner import run_mcp_server
from opsly.services.analyst import CodeAnalystService


def build_server() -> MCPServer:
    mcp = MCPServer("code-analyst-agent")
    svc = CodeAnalystService()

    @mcp.tool()
    def analyze_function(name: str) -> dict[str, Any]:
        return svc.analyze_function(name)

    @mcp.tool()
    def analyze_class(name: str) -> dict[str, Any]:
        return svc.analyze_class(name)

    @mcp.tool()
    def find_patterns(scope: str = "repository") -> dict[str, Any]:
        return svc.find_patterns(scope)

    @mcp.tool()
    def get_code_snippet(name: str, context_lines: int = 5) -> dict[str, Any]:
        return svc.get_code_snippet(name, context_lines)

    @mcp.tool()
    def explain_implementation(name: str) -> dict[str, Any]:
        return svc.explain_implementation(name)

    @mcp.tool()
    def compare_implementations(entity_a: str, entity_b: str) -> dict[str, Any]:
        return svc.compare_implementations(entity_a, entity_b)

    return mcp


def main() -> None:
    run_mcp_server(build_server(), default_port=9004)


if __name__ == "__main__":
    main()

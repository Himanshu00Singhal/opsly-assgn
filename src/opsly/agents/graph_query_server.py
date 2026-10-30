"""Graph Query MCP server."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from opsly.agents._runner import run_mcp_server
from opsly.graph.neo4j_store import Neo4jGraphStore


def build_server() -> MCPServer:
    mcp = MCPServer("graph-query-agent")
    graph = Neo4jGraphStore()

    @mcp.tool()
    def find_entity(name: str, entity_type: str | None = None) -> list[dict[str, Any]]:
        """Locate a class, function, or module by name."""
        return graph.find_entity(name, entity_type)

    @mcp.tool()
    def get_dependencies(fqn: str) -> list[dict[str, Any]]:
        """Find what an entity depends on."""
        return graph.get_dependencies(fqn)

    @mcp.tool()
    def get_dependents(fqn: str) -> list[dict[str, Any]]:
        """Find what depends on an entity."""
        return graph.get_dependents(fqn)

    @mcp.tool()
    def trace_imports(module_fqn: str) -> list[dict[str, Any]]:
        """Follow import chain for a module."""
        return graph.trace_imports(module_fqn)

    @mcp.tool()
    def find_related(fqn: str, relationship_type: str) -> list[dict[str, Any]]:
        """Get entities related by relationship type."""
        return graph.find_related(fqn, relationship_type)

    @mcp.tool()
    def execute_query(cypher: str, parameters_json: str = "{}") -> list[dict[str, Any]]:
        """Run a read-only Cypher query."""
        params = json.loads(parameters_json) if parameters_json else {}
        return graph.execute_query(cypher, params)

    return mcp


def main() -> None:
    run_mcp_server(build_server(), default_port=9003)


if __name__ == "__main__":
    main()

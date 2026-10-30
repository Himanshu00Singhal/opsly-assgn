"""Memory MCP server."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from opsly.agents._runner import run_mcp_server
from opsly.memory.store import get_memory_store


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def build_server() -> MCPServer:
    mcp = MCPServer("memory-agent")

    @mcp.tool()
    def save_turn(session_id: str, role: str, content: str) -> dict[str, str]:
        """Persist a conversation turn."""
        async def inner() -> None:
            store = await get_memory_store()
            await store.save_turn(session_id, role, content)

        _run(inner())
        return {"status": "ok"}

    @mcp.tool()
    def get_session_history(session_id: str, limit: int = 20) -> list[dict[str, str]]:
        """Return recent session messages."""

        async def inner() -> list[dict[str, str]]:
            store = await get_memory_store()
            return await store.get_session_history(session_id, limit)

        return _run(inner())

    @mcp.tool()
    def cache_agent_result(session_id: str, tool: str, args_json: str, result_json: str) -> dict[str, str]:
        """Cache agent tool output."""

        async def inner() -> None:
            store = await get_memory_store()
            await store.cache_agent_result(session_id, tool, json.loads(args_json), json.loads(result_json))

        _run(inner())
        return {"status": "ok"}

    @mcp.tool()
    def get_cached_result(session_id: str, tool: str, args_json: str) -> Any:
        """Fetch cached agent output."""

        async def inner() -> Any:
            store = await get_memory_store()
            return await store.get_cached_result(session_id, tool, json.loads(args_json))

        return _run(inner())

    @mcp.tool()
    def record_routing_decision(session_id: str, decision_json: str) -> dict[str, str]:
        """Store routing audit entry."""

        async def inner() -> None:
            store = await get_memory_store()
            await store.record_routing_decision(session_id, json.loads(decision_json))

        _run(inner())
        return {"status": "ok"}

    return mcp


def main() -> None:
    run_mcp_server(build_server(), default_port=9005)


if __name__ == "__main__":
    main()

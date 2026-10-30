"""Orchestrator MCP server."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from opsly.agents._runner import run_mcp_server
from opsly.mcp_client import call_mcp_tool
from opsly.shared.config import get_app_settings
from opsly.shared.llm import (
    analyze_query_rules,
    groq_chat,
    route_to_agents_rules,
    synthesize_template,
)


def build_server() -> MCPServer:
    mcp = MCPServer("orchestrator-agent")
    settings = get_app_settings()

    @mcp.tool()
    def analyze_query(query: str, session_id: str = "default") -> dict[str, Any]:
        """Classify query intent and extract key entities."""
        analysis = analyze_query_rules(query)
        llm = groq_chat(
            f"Classify this codebase question and list entities as JSON: {query}",
            purpose="routing",
        )
        if llm:
            analysis["llm_hint"] = llm[:500]
        analysis["session_id"] = session_id
        return analysis

    @mcp.tool()
    def route_to_agents(analysis_json: str) -> dict[str, Any]:
        """Determine which agents should handle the query."""
        analysis = json.loads(analysis_json)
        plan = route_to_agents_rules(analysis)
        return plan

    @mcp.tool()
    def get_conversation_context(session_id: str, limit: int = 10) -> dict[str, Any]:
        """Retrieve relevant conversation history via Memory agent."""

        async def inner() -> Any:
            return await call_mcp_tool(
                settings.mcp_memory_url,
                "get_session_history",
                {"session_id": session_id, "limit": limit},
            )

        history = asyncio.run(inner())
        return {"session_id": session_id, "history": history}

    @mcp.tool()
    def synthesize_response(message: str, agent_outputs_json: str) -> dict[str, str]:
        """Combine agent outputs into a coherent response."""
        outputs = json.loads(agent_outputs_json)
        prompt = (
            f"User question: {message}\n\nAgent data:\n{json.dumps(outputs)[:6000]}\n\n"
            "Write a helpful answer for a FastAPI codebase question."
        )
        text = groq_chat(prompt, purpose="synthesis")
        if not text:
            text = synthesize_template(message, outputs)
        return {"response": text}

    return mcp


def main() -> None:
    run_mcp_server(build_server(), default_port=9001)


if __name__ == "__main__":
    main()

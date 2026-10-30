# Chat path: orchestrator tools for plan + synthesis; gateway executes graph/code MCP calls.

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from opsly.mcp_client import call_mcp_tool
from opsly.shared.config import AppSettings

logger = logging.getLogger(__name__)

AGENT_URLS = {
    "orchestrator": "mcp_orchestrator_url",
    "indexer": "mcp_indexer_url",
    "graph_query": "mcp_graph_query_url",
    "code_analyst": "mcp_code_analyst_url",
    "memory": "mcp_memory_url",
}


def _url(settings: AppSettings, agent: str) -> str:
    key = AGENT_URLS[agent]
    return getattr(settings, key)


async def run_chat(
    settings: AppSettings,
    session_id: str,
    message: str,
) -> tuple[str, dict[str, Any]]:
    """Return final response and debug payload."""
    meta: dict[str, Any] = {"steps": []}

    analysis = await call_mcp_tool(
        _url(settings, "orchestrator"),
        "analyze_query",
        {"query": message, "session_id": session_id},
    )
    meta["steps"].append({"tool": "analyze_query", "result": analysis})

    context = await call_mcp_tool(
        _url(settings, "orchestrator"),
        "get_conversation_context",
        {"session_id": session_id},
    )
    meta["steps"].append({"tool": "get_conversation_context", "result": context})

    plan = await call_mcp_tool(
        _url(settings, "orchestrator"),
        "route_to_agents",
        {"analysis_json": json.dumps(analysis)},
    )
    meta["steps"].append({"tool": "route_to_agents", "result": plan})

    await call_mcp_tool(
        _url(settings, "memory"),
        "record_routing_decision",
        {"session_id": session_id, "decision_json": json.dumps(plan)},
    )

    agent_outputs: dict[str, Any] = {}
    entities = analysis.get("entities") or []
    primary = entities[0] if entities else "FastAPI"
    lower_msg = message.lower()
    entity_type: str | None = None
    if "class" in lower_msg:
        entity_type = "Class"
    elif "function" in lower_msg:
        entity_type = "Function"

    graph_args: dict[str, Any] = {"name": primary}
    if entity_type:
        graph_args["entity_type"] = entity_type

    for step in plan.get("parallel", []):
        agent = step.get("agent", "")
        tool = step.get("tool", "")
        try:
            if agent == "graph_query" and tool == "find_entity":
                out = await call_mcp_tool(
                    _url(settings, "graph_query"), "find_entity", graph_args
                )
                agent_outputs["graph_find_entity"] = out
                if isinstance(out, list) and out:
                    for hit in out:
                        if hit.get("docstring"):
                            agent_outputs["docstring"] = hit["docstring"]
                            break
            elif agent == "code_analyst" and tool == "get_code_snippet":
                snippet_name = primary
                if isinstance(agent_outputs.get("graph_find_entity"), list):
                    for hit in agent_outputs["graph_find_entity"]:
                        if hit.get("type") in ("Function", "Class") and not (
                            hit.get("path") or ""
                        ).startswith("tests/"):
                            snippet_name = hit.get("name") or primary
                            break
                out = await call_mcp_tool(
                    _url(settings, "code_analyst"),
                    "get_code_snippet",
                    {"name": snippet_name},
                )
                agent_outputs["code_snippet"] = out
                if out.get("docstring"):
                    agent_outputs["docstring"] = out["docstring"]
            elif agent == "code_analyst" and tool == "compare_implementations":
                a, b = (entities + ["Path", "Query"])[:2]
                out = await call_mcp_tool(
                    _url(settings, "code_analyst"),
                    "compare_implementations",
                    {"entity_a": a, "entity_b": b},
                )
                agent_outputs["compare"] = out
        except Exception as exc:
            logger.warning("Agent step failed: %s", exc)
            agent_outputs[f"{agent}_{tool}_error"] = str(exc)

    if analysis.get("intent") == "explain" and "code_snippet" not in agent_outputs:
        try:
            agent_outputs["explain"] = await call_mcp_tool(
                _url(settings, "code_analyst"),
                "explain_implementation",
                {"name": primary},
            )
        except Exception as exc:
            agent_outputs["explain_error"] = str(exc)

    synth = await call_mcp_tool(
        _url(settings, "orchestrator"),
        "synthesize_response",
        {"message": message, "agent_outputs_json": json.dumps(agent_outputs)},
    )
    response = synth.get("response", str(synth)) if isinstance(synth, dict) else str(synth)

    await call_mcp_tool(
        _url(settings, "memory"),
        "save_turn",
        {"session_id": session_id, "role": "user", "content": message},
    )
    await call_mcp_tool(
        _url(settings, "memory"),
        "save_turn",
        {"session_id": session_id, "role": "assistant", "content": response},
    )
    meta["agent_outputs"] = agent_outputs
    return response, meta


async def stream_chat_events(
    settings: AppSettings,
    session_id: str,
    message: str,
) -> AsyncIterator[dict[str, Any]]:
    yield {"event": "agent_start", "agent": "orchestrator"}
    response, meta = await run_chat(settings, session_id, message)
    yield {"event": "agent_done", "agent": "orchestrator", "meta": meta}
    yield {"event": "final", "response": response}

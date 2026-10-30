# HTTP entrypoint — not an MCP server; calls agents via mcp_client.

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from opsly.gateway.chat_flow import run_chat, stream_chat_events
from opsly.gateway.schemas import ChatRequest, ChatResponse, HealthResponse, IndexRequest, IndexResponse
from opsly.graph.neo4j_store import Neo4jGraphStore
from opsly.mcp_client import call_mcp_tool
from opsly.shared.config import AppSettings, get_app_settings
from opsly.shared.logging import bind_context, configure_logging

logger = logging.getLogger(__name__)

app = FastAPI(title="opsly-assgn gateway", version="0.1.0")


@app.on_event("startup")
def on_startup() -> None:
    settings = get_app_settings()
    configure_logging(settings.log_level)


def verify_api_key(
    settings: AppSettings = Depends(get_app_settings),
    x_api_key: str | None = Header(default=None),
) -> None:
    if settings.gateway_api_key and x_api_key != settings.gateway_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    settings: AppSettings = Depends(get_app_settings),
    x_request_id: str | None = Header(default=None),
    _: None = Depends(verify_api_key),
) -> ChatResponse | StreamingResponse:
    cid = x_request_id or str(uuid.uuid4())
    bind_context(correlation_id=cid, session_id=body.session_id)
    if body.stream:

        async def sse() -> Any:
            async for event in stream_chat_events(settings, body.session_id, body.message):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")

    try:
        response, meta = await run_chat(settings, body.session_id, body.message)
    except Exception as exc:
        logger.exception("Chat failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponse(session_id=body.session_id, response=response, meta=meta)


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    settings = get_app_settings()
    try:
        while True:
            payload = await websocket.receive_json()
            session_id = payload.get("session_id", "default")
            message = payload.get("message", "")
            async for event in stream_chat_events(settings, session_id, message):
                await websocket.send_json(event)
    except WebSocketDisconnect:
        return


@app.post("/api/index", response_model=IndexResponse)
async def index_repo(
    body: IndexRequest,
    settings: AppSettings = Depends(get_app_settings),
    _: None = Depends(verify_api_key),
) -> IndexResponse:
    result = await call_mcp_tool(
        settings.mcp_indexer_url,
        "index_repository",
        {"mode": body.mode},
    )
    job_id = result.get("job_id") if isinstance(result, dict) else str(result)
    return IndexResponse(job_id=job_id)


@app.get("/api/index/status/{job_id}")
async def index_status(
    job_id: str,
    settings: AppSettings = Depends(get_app_settings),
    _: None = Depends(verify_api_key),
) -> dict[str, Any]:
    return await call_mcp_tool(settings.mcp_indexer_url, "get_index_status", {"job_id": job_id})


async def _probe_agent(name: str, url: str) -> str:
    probes: dict[str, tuple[str, dict[str, object]]] = {
        "orchestrator": ("analyze_query", {"query": "health", "session_id": "health"}),
        "indexer": ("parse_python_ast", {"source": "def x(): pass", "file_path": "h.py"}),
        "graph_query": ("find_entity", {"name": "FastAPI"}),
        "code_analyst": ("find_patterns", {"scope": "health"}),
        "memory": ("get_session_history", {"session_id": "health", "limit": 1}),
    }
    tool, args = probes[name]
    try:
        await call_mcp_tool(url, tool, args)
        return "up"
    except Exception as exc:
        return f"down: {type(exc).__name__}"


@app.get("/api/agents/health", response_model=HealthResponse)
async def agents_health(settings: AppSettings = Depends(get_app_settings)) -> HealthResponse:
    agents = {
        "orchestrator": settings.mcp_orchestrator_url,
        "indexer": settings.mcp_indexer_url,
        "graph_query": settings.mcp_graph_query_url,
        "code_analyst": settings.mcp_code_analyst_url,
        "memory": settings.mcp_memory_url,
    }
    status: dict[str, str] = {}
    for name, url in agents.items():
        status[name] = await _probe_agent(name, url)
    try:
        Neo4jGraphStore().statistics()
        status["neo4j"] = "up"
    except Exception as exc:
        status["neo4j"] = f"down: {type(exc).__name__}"
    overall = "ok" if all(v == "up" for v in status.values()) else "degraded"
    return HealthResponse(status=overall, agents=status)


@app.get("/api/graph/statistics")
async def graph_statistics(_: None = Depends(verify_api_key)) -> dict[str, Any]:
    try:
        return Neo4jGraphStore().statistics()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def run() -> None:
    import uvicorn

    settings = get_app_settings()
    uvicorn.run(
        "opsly.gateway.main:app",
        host=settings.gateway_host,
        port=settings.gateway_port,
        reload=False,
    )


if __name__ == "__main__":
    run()

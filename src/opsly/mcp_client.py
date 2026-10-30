"""MCP streamable-HTTP client."""

from __future__ import annotations

import json
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _format_exception(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        parts = [_format_exception(e) for e in exc.exceptions]
        return "; ".join(parts)
    return f"{type(exc).__name__}: {exc}"


def _parse_tool_result(result: Any) -> Any:
    structured = getattr(result, "structured_content", None) or getattr(
        result, "structuredContent", None
    )
    if structured is not None:
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured
    texts: list[str] = []
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    joined = "\n".join(texts).strip()
    if not joined:
        return None
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return joined


async def call_mcp_tool(url: str, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Invoke a tool on a remote MCP server."""
    args = arguments or {}
    try:
        async with streamable_http_client(url, terminate_on_close=True) as streams:
            read, write = streams
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, args)
                if getattr(result, "is_error", False):
                    raise RuntimeError(f"MCP tool {tool_name} failed: {result.content}")
                return _parse_tool_result(result)
    except BaseException as exc:
        raise RuntimeError(f"MCP call to {url} tool {tool_name}: {_format_exception(exc)}") from exc

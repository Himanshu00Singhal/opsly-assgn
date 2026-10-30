# Query routing + answer templates when Groq isn't configured.

from __future__ import annotations

import json
import re
from typing import Any

from opsly.env_loader import groq_models_to_try
from opsly.shared.config import get_groq_settings


_ENTITY_STOPWORDS = frozenset(
    {"Show", "What", "Which", "The", "How", "Find", "List", "Explain", "Compare", "Me"}
)


def extract_entities(message: str) -> list[str]:
    patterns = [
        r"\b(FastAPI|APIRouter|Depends|Path|Query|HTTPException|Request|Response)\b",
        r"\b([A-Z][a-zA-Z0-9_]{2,})\b",
    ]
    found: list[str] = []
    for pat in patterns:
        for m in re.finditer(pat, message):
            name = m.group(1) if m.lastindex else m.group(0)
            if name in _ENTITY_STOPWORDS:
                continue
            if name not in found:
                found.append(name)
    return found[:10]


def analyze_query_rules(message: str) -> dict[str, Any]:
    lower = message.lower()
    if any(w in lower for w in ("compare", "difference", "vs")):
        intent = "compare"
    elif any(w in lower for w in ("explain", "how", "lifecycle", "work")):
        intent = "explain"
    elif any(w in lower for w in ("show", "snippet", "docstring")):
        intent = "show"
    elif any(w in lower for w in ("find", "list", "what", "which")):
        intent = "find"
    else:
        intent = "general"
    return {
        "intent": intent,
        "entities": extract_entities(message),
        "requires_graph": intent in {"find", "explain", "compare", "show"},
        "requires_code": intent in {"explain", "compare", "show"},
    }


def route_to_agents_rules(analysis: dict[str, Any]) -> dict[str, Any]:
    parallel: list[dict[str, str]] = []
    if analysis.get("requires_graph"):
        parallel.append({"agent": "graph_query", "tool": "find_entity", "arg_key": "name"})
    if analysis.get("requires_code"):
        parallel.append({"agent": "code_analyst", "tool": "get_code_snippet", "arg_key": "name"})
    if analysis.get("intent") == "compare":
        parallel.append({"agent": "code_analyst", "tool": "compare_implementations", "arg_key": "entity_a"})
    return {
        "parallel": parallel,
        "sequential": [],
        "fallback": [{"agent": "graph_query", "tool": "find_entity"}],
    }


def synthesize_template(message: str, agent_outputs: dict[str, Any]) -> str:
    lower = message.lower()
    if "docstring" in lower:
        doc = agent_outputs.get("docstring")
        hits = agent_outputs.get("graph_find_entity")
        if not doc and isinstance(hits, list):
            for hit in hits:
                if hit.get("docstring"):
                    doc = hit["docstring"]
                    break
        snippet = agent_outputs.get("code_snippet") or {}
        name = snippet.get("name") or (hits[0]["name"] if isinstance(hits, list) and hits else "entity")
        path = snippet.get("file_path") or (
            hits[0].get("path") if isinstance(hits, list) and hits else "unknown"
        )
        if doc:
            body = doc
        elif snippet.get("snippet"):
            body = snippet["snippet"][:2000]
        else:
            body = json.dumps(agent_outputs, indent=2)[:3000]
        return f"**{name}** (`{path}`)\n\n{body}"

    if "class" in lower and isinstance(agent_outputs.get("graph_find_entity"), list):
        hits = [h for h in agent_outputs["graph_find_entity"] if h.get("type") == "Class"]
        if hits:
            hit = hits[0]
            doc = hit.get("docstring") or "(no docstring indexed)"
            return f"**Class {hit.get('name')}** — `{hit.get('path')}`\n\n{doc}"

    parts = [message, ""]
    for key, value in agent_outputs.items():
        if key == "graph_find_entity" and isinstance(value, list):
            parts.append(f"## {key} (top 3)")
            parts.append(json.dumps(value[:3], indent=2))
        else:
            parts.append(f"## {key}")
            parts.append(json.dumps(value, indent=2)[:4000])
        parts.append("")
    return "\n".join(parts).strip()


def groq_chat(prompt: str, *, purpose: str = "synthesis") -> str | None:
    settings = get_groq_settings()
    if not settings.groq_api_key:
        return None
    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    models = groq_models_to_try("routing" if purpose == "routing" else "synthesis")
    for model in models:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            continue
    return None

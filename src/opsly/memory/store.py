"""SQLite-backed conversation memory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import aiosqlite

from opsly.shared.config import get_app_settings
from opsly.shared.exceptions import MemoryError


class MemoryStore:
    def __init__(self, db_path: str | None = None) -> None:
        settings = get_app_settings()
        self._path = Path(db_path or settings.memory_db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS routing_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS agent_cache (
                    cache_key TEXT PRIMARY KEY,
                    result_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await db.commit()

    async def save_turn(self, session_id: str, role: str, content: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO turns (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            await db.commit()

    async def get_session_history(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT role, content FROM turns
                WHERE session_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (session_id, limit),
            )
            rows = await cur.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def record_routing_decision(self, session_id: str, decision: dict[str, Any]) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO routing_log (session_id, decision_json) VALUES (?, ?)",
                (session_id, json.dumps(decision)),
            )
            await db.commit()

    async def cache_agent_result(
        self, session_id: str, tool: str, args: dict[str, Any], result: Any
    ) -> None:
        key = self._cache_key(session_id, tool, args)
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO agent_cache (cache_key, result_json) VALUES (?, ?)
                """,
                (key, json.dumps(result)),
            )
            await db.commit()

    async def get_cached_result(
        self, session_id: str, tool: str, args: dict[str, Any]
    ) -> Any | None:
        key = self._cache_key(session_id, tool, args)
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT result_json FROM agent_cache WHERE cache_key = ?", (key,)
            )
            row = await cur.fetchone()
        if not row:
            return None
        return json.loads(row[0])

    @staticmethod
    def _cache_key(session_id: str, tool: str, args: dict[str, Any]) -> str:
        raw = f"{session_id}:{tool}:{json.dumps(args, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()


async def get_memory_store() -> MemoryStore:
    store = MemoryStore()
    try:
        await store.init()
    except Exception as exc:
        raise MemoryError(str(exc)) from exc
    return store

import asyncio
from pathlib import Path

from opsly.memory.store import MemoryStore


def test_memory_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "mem.db"
    store = MemoryStore(str(db))

    async def run() -> None:
        await store.init()
        await store.save_turn("s1", "user", "hello")
        await store.save_turn("s1", "assistant", "hi")
        hist = await store.get_session_history("s1")
        assert len(hist) == 2
        await store.cache_agent_result("s1", "find_entity", {"name": "FastAPI"}, [{"fqn": "x"}])
        cached = await store.get_cached_result("s1", "find_entity", {"name": "FastAPI"})
        assert cached == [{"fqn": "x"}]

    asyncio.run(run())

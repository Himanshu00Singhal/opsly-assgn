import pytest

from opsly.graph.neo4j_store import FORBIDDEN_CYPHER, Neo4jGraphStore
from opsly.shared.exceptions import GraphQueryError


def test_forbidden_cypher_detected() -> None:
    assert FORBIDDEN_CYPHER.search("CREATE (n:Test)")


def test_execute_query_blocks_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    store = Neo4jGraphStore.__new__(Neo4jGraphStore)
    with pytest.raises(GraphQueryError):
        store.execute_query("CREATE (n:Bad) RETURN n")

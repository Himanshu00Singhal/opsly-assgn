"""Neo4j graph persistence and queries."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, Session

from opsly.graph.parser import ParseResult, ParsedEntity, ParsedRelation
from opsly.shared.config import Neo4jSettings, get_neo4j_settings
from opsly.shared.exceptions import GraphQueryError, IndexingError

FORBIDDEN_CYPHER = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|DROP|SET|REMOVE|CALL\s+dbms)\b",
    re.IGNORECASE,
)


class Neo4jGraphStore:
    def __init__(self, settings: Neo4jSettings | None = None) -> None:
        self._settings = settings or get_neo4j_settings()
        self._driver = GraphDatabase.driver(
            self._settings.neo4j_uri,
            auth=(self._settings.neo4j_user, self._settings.neo4j_password),
        )

    def close(self) -> None:
        self._driver.close()

    def _session(self) -> Session:
        return self._driver.session(database=self._settings.neo4j_database)

    async def run_async(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(func, *args, **kwargs)

    def apply_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.cypher")
        with self._session() as session:
            for stmt in schema_path.read_text(encoding="utf-8").split(";"):
                q = stmt.strip()
                if q:
                    session.run(q)

    def upsert_parse_result(self, result: ParseResult) -> None:
        with self._session() as session:
            for ent in result.entities:
                session.run(
                    f"""
                    MERGE (n:{ent.label} {{fqn: $fqn}})
                    SET n.name = $name, n.file_path = $file_path,
                        n.line_start = $line_start, n.line_end = $line_end,
                        n.docstring = $docstring
                    """,
                    fqn=ent.fqn,
                    name=ent.name,
                    file_path=ent.file_path,
                    line_start=ent.line_start,
                    line_end=ent.line_end,
                    docstring=ent.docstring,
                )
            for rel in result.relations:
                session.run(
                    f"""
                    MATCH (a {{fqn: $from_fqn}}), (b {{fqn: $to_fqn}})
                    MERGE (a)-[:{rel.rel_type}]->(b)
                    """,
                    from_fqn=rel.from_fqn,
                    to_fqn=rel.to_fqn,
                )

    def statistics(self) -> dict[str, Any]:
        with self._session() as session:
            total_nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            total_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            by_label = session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c ORDER BY c DESC"
            )
            return {
                "total_nodes": total_nodes,
                "total_relationships": total_rels,
                "by_label": {r["label"]: r["c"] for r in by_label if r["label"]},
            }

    @staticmethod
    def _rank_entity_hit(name: str, row: dict[str, Any]) -> tuple[int, int, int, int]:
        path = row.get("path") or ""
        typ = row.get("type") or ""
        nm = row.get("name") or ""
        # Prefer library code over tests/ when names fuzzy-match (e.g. Depends vs test_*_depends).
        test_penalty = 100 if path.startswith("tests/") or "/test_" in path else 0
        type_rank = {"Function": 0, "Class": 1, "Method": 2, "Module": 3}.get(typ, 8)
        if nm == name:
            exact = 0
        elif nm.lower() == name.lower():
            exact = 1
        elif name.lower() in nm.lower():
            exact = 2
        else:
            exact = 3
        return (test_penalty, type_rank, exact, len(path))

    def find_entity(self, name: str, entity_type: str | None = None) -> list[dict[str, Any]]:
        query = """
        MATCH (n)
        WHERE (
            toLower(n.name) = toLower($name)
            OR n.fqn ENDS WITH $suffix
            OR toLower(n.name) CONTAINS toLower($name)
            OR toLower(n.fqn) CONTAINS toLower($dotted)
        )
        """
        if entity_type:
            query += " AND $entity_type IN labels(n)"
        query += """
        RETURN labels(n)[0] AS type, n.fqn AS fqn, n.name AS name,
               n.file_path AS path, n.docstring AS docstring
        LIMIT 80
        """
        params: dict[str, Any] = {
            "name": name,
            "suffix": f".{name}",
            "dotted": f".{name.lower()}",
        }
        if entity_type:
            params["entity_type"] = entity_type
        with self._session() as session:
            rows = [dict(r) for r in session.run(query, **params)]
        rows.sort(key=lambda r: self._rank_entity_hit(name, r))
        return rows[:15]

    def get_dependencies(self, fqn: str) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = session.run(
                """
                MATCH (n {fqn: $fqn})-[r:IMPORTS|DEPENDS_ON|INHERITS_FROM]->(d)
                RETURN type(r) AS rel, labels(d)[0] AS type, d.fqn AS fqn, d.name AS name
                """,
                fqn=fqn,
            )
            return [dict(r) for r in rows]

    def get_dependents(self, fqn: str) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = session.run(
                """
                MATCH (d)-[r:IMPORTS|DEPENDS_ON|INHERITS_FROM|CALLS]->(n {fqn: $fqn})
                RETURN type(r) AS rel, labels(d)[0] AS type, d.fqn AS fqn, d.name AS name
                """,
                fqn=fqn,
            )
            return [dict(r) for r in rows]

    def trace_imports(self, module_fqn: str) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = session.run(
                """
                MATCH (m:Module {fqn: $module_fqn})-[:IMPORTS*1..3]->(i)
                RETURN DISTINCT labels(i)[0] AS type, i.fqn AS fqn, i.name AS name
                LIMIT 50
                """,
                module_fqn=module_fqn,
            )
            return [dict(r) for r in rows]

    def find_related(self, fqn: str, relationship_type: str) -> list[dict[str, Any]]:
        rel = relationship_type.upper().replace(" ", "_")
        with self._session() as session:
            rows = session.run(
                f"""
                MATCH (n {{fqn: $fqn}})-[:{rel}]->(x)
                RETURN labels(x)[0] AS type, x.fqn AS fqn, x.name AS name
                LIMIT 50
                """,
                fqn=fqn,
            )
            return [dict(r) for r in rows]

    def execute_query(self, cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if FORBIDDEN_CYPHER.search(cypher):
            raise GraphQueryError("Write operations are not allowed in execute_query")
        params = parameters or {}
        with self._session() as session:
            try:
                return [dict(r) for r in session.run(cypher, **params)]
            except Exception as exc:
                raise GraphQueryError(str(exc)) from exc

    def clear_graph(self) -> None:
        with self._session() as session:
            session.run("MATCH (n) DETACH DELETE n")

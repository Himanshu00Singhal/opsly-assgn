"""Indexer MCP server."""

from __future__ import annotations

import threading

from mcp.server.mcpserver import MCPServer

from opsly.agents._runner import run_mcp_server
from opsly.services.indexer import IndexerService


def build_server() -> MCPServer:
    mcp = MCPServer("indexer-agent")
    svc = IndexerService()

    @mcp.tool()
    def index_repository(mode: str = "full") -> dict[str, str]:
        """Full or incremental repository indexing."""
        job_id = svc.start_job("incremental" if mode == "incremental" else "full")
        threading.Thread(target=svc.run_job, args=(job_id,), daemon=True).start()
        return {"job_id": job_id, "status": "started"}

    @mcp.tool()
    def index_file(file_path: str) -> dict[str, object]:
        """Index a single Python file."""
        return svc.index_file(file_path)

    @mcp.tool()
    def parse_python_ast(source: str, file_path: str = "inline.py") -> dict[str, object]:
        """Extract AST entities from Python source."""
        return svc.parse_ast(source, file_path)

    @mcp.tool()
    def extract_entities(source: str, file_path: str = "inline.py") -> dict[str, object]:
        """Identify code entities and relationships."""
        return svc.extract_entities(source, file_path)

    @mcp.tool()
    def get_index_status(job_id: str) -> dict[str, object]:
        """Report indexing progress."""
        return svc.get_status(job_id)

    return mcp


def main() -> None:
    run_mcp_server(build_server(), default_port=9002)


if __name__ == "__main__":
    main()

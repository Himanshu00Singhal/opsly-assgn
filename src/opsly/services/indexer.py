"""Repository indexing service."""

from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from opsly.graph.neo4j_store import Neo4jGraphStore
from opsly.graph.parser import parse_file_path, parse_python_ast
from opsly.shared.config import get_app_settings
from opsly.shared.exceptions import IndexingError

IndexMode = Literal["full", "incremental"]


@dataclass
class IndexJob:
    job_id: str
    mode: IndexMode
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    progress: float = 0.0
    message: str = ""
    stats: dict[str, Any] = field(default_factory=dict)


_JOBS: dict[str, IndexJob] = {}


class IndexerService:
    def __init__(self) -> None:
        self._settings = get_app_settings()
        self._graph = Neo4jGraphStore()

    def ensure_repo(self) -> Path:
        repo = Path(self._settings.fastapi_repo_path)
        if not repo.exists():
            repo.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--depth", "1", self._settings.fastapi_repo_url, str(repo)],
                check=True,
                capture_output=True,
            )
        return repo

    def start_job(self, mode: IndexMode = "full") -> str:
        job_id = str(uuid.uuid4())
        _JOBS[job_id] = IndexJob(job_id=job_id, mode=mode)
        return job_id

    def run_job(self, job_id: str) -> None:
        job = _JOBS.get(job_id)
        if not job:
            raise IndexingError(f"Unknown job {job_id}")
        job.status = "running"
        try:
            repo = self.ensure_repo()
            if job.mode == "full":
                self._graph.clear_graph()
            self._graph.apply_schema()
            py_files = [p for p in repo.rglob("*.py") if ".git" not in p.parts]
            total = max(len(py_files), 1)
            indexed = 0
            entities = 0
            for path in py_files:
                rel = path.relative_to(repo).as_posix()
                try:
                    result = parse_file_path(path, repo)
                    self._graph.upsert_parse_result(result)
                    entities += len(result.entities)
                except Exception:
                    continue
                indexed += 1
                job.progress = round(100.0 * indexed / total, 2)
                job.message = f"Indexed {indexed}/{total} files"
            job.stats = self._graph.statistics()
            job.stats["entities_indexed"] = entities
            job.status = "completed"
            job.progress = 100.0
        except Exception as exc:
            job.status = "failed"
            job.message = str(exc)
            raise IndexingError(str(exc)) from exc

    def get_status(self, job_id: str) -> dict[str, Any]:
        job = _JOBS.get(job_id)
        if not job:
            raise IndexingError(f"Unknown job {job_id}")
        return {
            "job_id": job.job_id,
            "mode": job.mode,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "stats": job.stats,
        }

    def index_file(self, file_path: str) -> dict[str, Any]:
        repo = self.ensure_repo()
        path = repo / file_path
        if not path.is_file():
            raise IndexingError(f"File not found: {file_path}")
        result = parse_file_path(path)
        self._graph.upsert_parse_result(result)
        return {"file": file_path, "entities": len(result.entities)}

    def parse_ast(self, source: str, file_path: str = "inline.py") -> dict[str, Any]:
        result = parse_python_ast(source, file_path)
        return {
            "entities": [e.__dict__ for e in result.entities],
            "relations": [r.__dict__ for r in result.relations],
        }

    def extract_entities(self, source: str, file_path: str = "inline.py") -> dict[str, Any]:
        return self.parse_ast(source, file_path)

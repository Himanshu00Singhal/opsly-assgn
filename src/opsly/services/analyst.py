"""Code analysis service."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from opsly.graph.neo4j_store import Neo4jGraphStore
from opsly.shared.config import get_app_settings
from opsly.shared.exceptions import AnalysisError


class CodeAnalystService:
    def __init__(self) -> None:
        self._settings = get_app_settings()
        self._graph = Neo4jGraphStore()

    def _repo_root(self) -> Path:
        return Path(self._settings.fastapi_repo_path)

    def _resolve_path(self, file_path: str) -> Path:
        path = self._repo_root() / file_path
        if not path.is_file():
            raise AnalysisError(f"Missing file {file_path}")
        return path

    def _scan_repo_for_def(self, name: str, context_lines: int) -> dict[str, Any] | None:
        root = self._repo_root()
        if not root.is_dir():
            return None
        pattern = re.compile(rf"^\s*(async\s+)?def\s+{re.escape(name)}\b")
        class_pattern = re.compile(rf"^\s*class\s+{re.escape(name)}\b")
        for path in sorted(root.rglob("*.py")):
            if "tests" in path.parts or path.parts[0:1] == ("docs",):
                continue
            rel = path.relative_to(root).as_posix()
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            for idx, line in enumerate(lines):
                if pattern.search(line) or class_pattern.search(line):
                    start = max(idx - context_lines, 0)
                    end = min(idx + context_lines + 20, len(lines))
                    return {
                        "name": name,
                        "file_path": rel,
                        "snippet": "\n".join(lines[start:end]),
                    }
        return None

    def get_code_snippet(self, name: str, context_lines: int = 5) -> dict[str, Any]:
        matches = self._graph.find_entity(name)
        if matches:
            match = matches[0]
            path = self._resolve_path(match["path"])
            lines = path.read_text(encoding="utf-8").splitlines()
            for idx, line in enumerate(lines):
                if re.search(rf"\b(class|def)\s+{re.escape(name)}\b", line):
                    start = max(idx - context_lines, 0)
                    end = min(idx + context_lines + 20, len(lines))
                    return {
                        "name": name,
                        "file_path": match["path"],
                        "snippet": "\n".join(lines[start:end]),
                        "docstring": match.get("docstring"),
                    }
        fallback = self._scan_repo_for_def(name, context_lines)
        if fallback:
            return fallback
        if not matches:
            raise AnalysisError(f"No entity named {name}")
        match = matches[0]
        path = self._resolve_path(match["path"])
        lines = path.read_text(encoding="utf-8").splitlines()
        return {"name": name, "file_path": match["path"], "snippet": "\n".join(lines[:40])}

    def analyze_function(self, name: str) -> dict[str, Any]:
        snippet = self.get_code_snippet(name)
        tree = ast.parse(snippet["snippet"])
        funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        detail = funcs[0].name if funcs else name
        return {"function": detail, "analysis": snippet, "complexity_hint": len(funcs)}

    def analyze_class(self, name: str) -> dict[str, Any]:
        snippet = self.get_code_snippet(name)
        return {"class": name, "analysis": snippet}

    def find_patterns(self, scope: str = "repository") -> dict[str, Any]:
        patterns = {"decorator_factory": 0, "dependency_injection": 0, "router": 0}
        root = self._repo_root()
        if not root.exists():
            return {"scope": scope, "patterns": patterns}
        for path in list(root.rglob("*.py"))[:200]:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "@router" in text or "APIRouter" in text:
                patterns["router"] += 1
            if "Depends(" in text:
                patterns["dependency_injection"] += 1
            if "def decorator" in text or "wraps(" in text:
                patterns["decorator_factory"] += 1
        return {"scope": scope, "patterns": patterns}

    def explain_implementation(self, name: str) -> dict[str, Any]:
        snippet = self.get_code_snippet(name)
        return {
            "name": name,
            "summary": f"Implementation excerpt for {name} from FastAPI source.",
            "snippet": snippet,
        }

    def compare_implementations(self, entity_a: str, entity_b: str) -> dict[str, Any]:
        return {
            "entity_a": self.get_code_snippet(entity_a),
            "entity_b": self.get_code_snippet(entity_b),
            "note": "Compare parameter handling, validation, and docstrings manually or via LLM synthesis.",
        }

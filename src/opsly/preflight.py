"""Preflight checks before building the MCP multi-agent assignment."""

from __future__ import annotations

import importlib
import os
import platform
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.request import Request, urlopen

from opsly import env_loader
from opsly.env_loader import groq_models_to_try

Status = Literal["pass", "warn", "fail", "skip"]

__all__ = [
    "CheckResult",
    "discover_root",
    "load_project_env",
    "ready_to_build",
    "run_all_checks",
    "summarize",
]


def load_project_env(root: Path) -> str:
    """Load `.env` or `keys.txt`. Defined here so notebooks can import from preflight."""
    return env_loader.load_project_env(root)


@dataclass(frozen=True)
class CheckResult:
    category: str
    name: str
    status: Status
    detail: str


def _mask(value: str, show: int = 4) -> str:
    value = value.strip()
    if not value:
        return "(empty)"
    if len(value) <= show * 2:
        return "*" * len(value)
    return f"{value[:show]}…{value[-show:]}"


def discover_root(start: Path | None = None) -> Path:
    """Project root (directory containing pyproject.toml)."""
    here = (start or Path.cwd()).resolve()
    for path in (here, *here.parents):
        if (path / "pyproject.toml").is_file():
            return path
    return here


def run_all_checks(root: Path | None = None) -> list[CheckResult]:
    root = discover_root(root)
    env_source = load_project_env(root)
    results: list[CheckResult] = []

    # --- Runtime ---
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 11) and (major, minor) < (3, 14):
        results.append(
            CheckResult("runtime", "python_version", "pass", f"{sys.version.split()[0]} ({platform.system()})")
        )
    elif (major, minor) >= (3, 14):
        results.append(
            CheckResult(
                "runtime",
                "python_version",
                "warn",
                f"{sys.version.split()[0]} — use 3.12 venv (pyproject requires <3.14)",
            )
        )
    else:
        results.append(
            CheckResult("runtime", "python_version", "fail", f"{sys.version.split()[0]} — need 3.11+")
        )

    venv_dir = (root / ".venv").resolve()
    if venv_dir.is_dir() and Path(sys.prefix).resolve() == venv_dir:
        results.append(CheckResult("runtime", "virtualenv", "pass", str(venv_dir)))
    elif (root / ".venv").is_dir():
        results.append(
            CheckResult(
                "runtime",
                "virtualenv",
                "warn",
                f"Using {sys.executable} — select kernel Python 3.12 (opsly-assgn .venv)",
            )
        )
    else:
        results.append(CheckResult("runtime", "virtualenv", "fail", "No .venv; run: python3.12 -m venv .venv"))

    # --- Dependencies ---
    packages = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "pydantic_settings",
        "httpx",
        "groq",
        "neo4j",
        "mcp",
        "dotenv",
        "structlog",
        "aiosqlite",
    ]
    for pkg in packages:
        mod = "dotenv" if pkg == "dotenv" else pkg
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "?")
            results.append(CheckResult("dependencies", pkg, "pass", f"v{ver}"))
        except ImportError as exc:
            results.append(CheckResult("dependencies", pkg, "fail", str(exc)))

    # --- Secrets / config ---
    if env_source == ".env":
        results.append(CheckResult("config", "env_file", "pass", "Loaded .env"))
    elif env_source == "keys.txt":
        results.append(
            CheckResult(
                "config",
                "env_file",
                "warn",
                "No .env — loaded keys.txt (run ./scripts/bootstrap_env.sh to create .env)",
            )
        )
    else:
        results.append(
            CheckResult(
                "config",
                "env_file",
                "fail",
                "Copy env.example to .env or add keys.txt",
            )
        )

    required_env = [
        "GROQ_API_KEY",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
    ]
    for key in required_env:
        val = os.getenv(key, "").strip()
        if key == "NEO4J_USER" and not val:
            val = os.getenv("NEO4J_USERNAME", "").strip()
        if val:
            results.append(CheckResult("config", key, "pass", _mask(val)))
        elif key == "GROQ_API_KEY":
            results.append(
                CheckResult("config", key, "warn", "Unset — LLM fallback mode only")
            )
        else:
            results.append(CheckResult("config", key, "fail", "Not set in .env"))

    # --- Groq live ---
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        from groq import Groq

        client = Groq(api_key=groq_key)
        last_err: Exception | None = None
        for model in groq_models_to_try("routing"):
            try:
                r = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Reply with exactly: ok"}],
                    max_tokens=16,
                )
                text = (r.choices[0].message.content or "").strip()
                os.environ.setdefault("GROQ_MODEL_ROUTING", model)
                results.append(
                    CheckResult(
                        "integrations",
                        "groq_api",
                        "pass",
                        f"model={model}, reply_len={len(text)}",
                    )
                )
                break
            except Exception as exc:
                last_err = exc
        else:
            results.append(
                CheckResult(
                    "integrations",
                    "groq_api",
                    "fail",
                    f"{type(last_err).__name__}: {last_err}",
                )
            )

    # --- Neo4j live ---
    uri = os.getenv("NEO4J_URI", "").strip()
    configured_user = os.getenv("NEO4J_USER", os.getenv("NEO4J_USERNAME", "")).strip()
    password = os.getenv("NEO4J_PASSWORD", "").strip()
    configured_db = os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j"
    if uri and password:
        from neo4j import GraphDatabase

        users: list[str] = []
        for candidate in (configured_user, "neo4j"):
            if candidate and candidate not in users:
                users.append(candidate)
        databases: list[str] = []
        for candidate in ("neo4j", configured_db):
            if candidate and candidate not in databases:
                databases.append(candidate)

        connected = False
        last_err: Exception | None = None
        for user in users:
            driver = GraphDatabase.driver(
                uri,
                auth=(user, password),
                connection_timeout=20,
            )
            for database in databases:
                try:
                    with driver.session(database=database) as session:
                        rec = session.run("RETURN 1 AS n").single()
                        assert rec and rec["n"] == 1
                        count_rec = session.run("MATCH (n) RETURN count(n) AS c").single()
                        node_count = count_rec["c"] if count_rec else 0
                    driver.close()
                    os.environ.setdefault("NEO4J_USER", user)
                    os.environ.setdefault("NEO4J_DATABASE", database)
                    status: Status = "pass" if node_count > 0 else "warn"
                    detail = f"user={user}, db={database}, nodes={node_count}"
                    if node_count == 0:
                        detail += " — empty graph until indexer runs"
                    results.append(CheckResult("integrations", "neo4j_aura", status, detail))
                    connected = True
                    break
                except Exception as exc:
                    last_err = exc
            if connected:
                break
            driver.close()
        if not connected:
            host = uri.replace("neo4j+s://", "").replace("neo4j://", "").split(":")[0]
            dns_ok = False
            try:
                socket.gethostbyname(host)
                dns_ok = True
            except OSError:
                dns_ok = False
            err_text = str(last_err or "")
            hint = (
                "Open https://console.neo4j.io — resume/start the instance; "
                "username is usually `neo4j`. For assignment dev you can use local Neo4j in Docker Compose."
            )
            routing_paused = "Unable to retrieve routing information" in err_text
            if routing_paused and dns_ok:
                status = "warn"
                detail = f"Aura reachable via DNS but Bolt routing failed (instance paused/stopped?). {hint}"
            elif not dns_ok:
                status = "fail"
                detail = f"DNS failed for {host}. {hint}"
            else:
                status = "fail"
                detail = f"{type(last_err).__name__}: {last_err} — {hint}"
            results.append(CheckResult("integrations", "neo4j_aura", status, detail))
    elif uri:
        results.append(CheckResult("integrations", "neo4j_aura", "fail", "Missing NEO4J_PASSWORD"))

    # --- Docker ---
    for name, cmd in (
        ("docker", ["docker", "version", "--format", "{{.Server.Version}}"]),
        ("docker_compose", ["docker", "compose", "version", "--short"]),
    ):
        if not shutil.which(cmd[0]):
            results.append(CheckResult("tooling", name, "fail", f"{cmd[0]} not on PATH"))
            continue
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=True)
            results.append(CheckResult("tooling", name, "pass", out.stdout.strip() or "ok"))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            results.append(CheckResult("tooling", name, "fail", str(exc)))

    # --- Git ---
    if (root / ".git").is_dir():
        try:
            remote = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            results.append(CheckResult("repo", "git_remote", "pass", remote.stdout.strip()))
        except subprocess.CalledProcessError:
            results.append(CheckResult("repo", "git_remote", "warn", "No origin remote"))
    else:
        results.append(CheckResult("repo", "git", "fail", "Not a git repository"))

    for doc in ("ass.md", "HOW_TO_USE.md", "pyproject.toml", "README.md"):
        path = root / doc
        if path.is_file():
            results.append(CheckResult("repo", doc, "pass", f"{path.stat().st_size} bytes"))
        else:
            results.append(CheckResult("repo", doc, "fail", "Missing"))

    # --- Network (optional) ---
    for label, url in (
        ("github", "https://github.com"),
        ("groq_api", "https://api.groq.com"),
    ):
        try:
            req = Request(url, method="HEAD")
            with urlopen(req, timeout=8) as resp:
                results.append(CheckResult("network", label, "pass", f"HTTP {resp.status}"))
        except Exception as exc:
            results.append(CheckResult("network", label, "warn", f"{type(exc).__name__}"))

    # --- Assignment implementation (expected failures until build) ---
    impl_paths = {
        "docker_compose.yml": root / "docker-compose.yml",
        "gateway_main": root / "src" / "gateway" / "main.py",
        "agent_orchestrator": root / "src" / "agents" / "orchestrator" / "server.py",
        "neo4j_schema": root / "src" / "graph" / "schema.cypher",
    }
    for name, path in impl_paths.items():
        if path.is_file():
            results.append(CheckResult("implementation", name, "pass", str(path.relative_to(root))))
        else:
            results.append(
                CheckResult("implementation", name, "skip", "Not built yet — next phase after preflight")
            )

    return results


def summarize(results: list[CheckResult]) -> dict[str, int]:
    counts = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for r in results:
        counts[r.status] += 1
    return counts


def ready_to_build(results: list[CheckResult]) -> bool:
    """True when environment is OK; implementation skips do not block."""
    blocking = [r for r in results if r.status == "fail" and r.category != "implementation"]
    return len(blocking) == 0

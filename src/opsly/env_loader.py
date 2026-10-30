"""Load environment from `.env` or `keys.txt` (KEY=VALUE lines only)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

_ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Groq model IDs change by account; try env first, then common IDs.
GROQ_MODEL_FALLBACKS = (
    "qwen/qwen3-32b",
    "qwen/qwen3.8-27b",
    "qwen/qwen3-8-27b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
)


def parse_keys_txt(path: Path) -> dict[str, str]:
    """Parse `keys.txt` without treating embedded Python as env syntax."""
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not _ENV_KEY.match(key):
            continue
        found[key] = value.strip()
    return found


def apply_parsed_env(values: dict[str, str]) -> None:
    """Apply parsed values and normalize Aura-style Neo4j keys."""
    for key, value in values.items():
        os.environ[key] = value
    if "NEO4J_USERNAME" in values and "NEO4J_USER" not in values:
        os.environ["NEO4J_USER"] = values["NEO4J_USERNAME"]


def load_project_env(root: Path) -> str:
    """Load `.env`, else `keys.txt`. Returns source label."""
    env_path = root / ".env"
    keys_path = root / "keys.txt"
    if env_path.is_file():
        load_dotenv(env_path, override=True)
        return ".env"
    if keys_path.is_file():
        apply_parsed_env(parse_keys_txt(keys_path))
        return "keys.txt"
    return "none"


def groq_models_to_try(purpose: str = "routing") -> list[str]:
    """Models to try for Groq (routing vs synthesis env vars)."""
    env_key = "GROQ_MODEL_ROUTING" if purpose == "routing" else "GROQ_MODEL_SYNTHESIS"
    preferred = os.getenv(env_key, "").strip()
    ordered: list[str] = []
    if preferred:
        ordered.append(preferred)
    for model in GROQ_MODEL_FALLBACKS:
        if model not in ordered:
            ordered.append(model)
    return ordered

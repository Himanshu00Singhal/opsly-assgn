#!/usr/bin/env bash
# Build .env from keys.txt (local only). keys.txt must never be committed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEYS="${ROOT}/keys.txt"
ENV="${ROOT}/.env"

if [[ ! -f "$KEYS" ]]; then
  echo "Missing ${KEYS}. Copy .env.example to .env and fill values manually."
  exit 1
fi

python3.12 <<'PY' "$KEYS" "$ENV"
import re
import sys
from pathlib import Path

keys_path = Path(sys.argv[1])
env_path = Path(sys.argv[2])
raw = keys_path.read_text(encoding="utf-8")

mapping = {
    "NEO4J_URI": "NEO4J_URI",
    "NEO4J_USERNAME": "NEO4J_USER",
    "NEO4J_PASSWORD": "NEO4J_PASSWORD",
    "NEO4J_DATABASE": "NEO4J_DATABASE",
    "GROQ_API_KEY": "GROQ_API_KEY",
}

found: dict[str, str] = {}
for line in raw.splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    m = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
    if m:
        found[m.group(1)] = m.group(2)

defaults = {
    "APP_ENV": "development",
    "LOG_LEVEL": "INFO",
    "LLM_PROVIDER": "groq",
    "GROQ_MODEL_SYNTHESIS": "qwen/qwen3-32b",
    "GROQ_MODEL_ROUTING": "qwen/qwen3-32b",
    "FASTAPI_REPO_PATH": "./data/repos/fastapi",
    "GATEWAY_HOST": "0.0.0.0",
    "GATEWAY_PORT": "8000",
    "MEMORY_DB_PATH": "./data/memory/sessions.db",
}

out: dict[str, str] = dict(defaults)
for src, dst in mapping.items():
    if src in found:
        out[dst] = found[src]

if "NEO4J_USER" not in out and "NEO4J_USERNAME" in found:
    out["NEO4J_USER"] = found["NEO4J_USERNAME"]

lines = [f"{k}={v}" for k, v in out.items()]
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Wrote {env_path} ({len(lines)} variables). Do not commit this file.")
PY

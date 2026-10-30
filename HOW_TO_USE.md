# How to use opsly-assgn

Single guide for **reviewers and new developers**: run the stack, index FastAPI, chat, verify, and optional local dev.

**Requirements:** Docker Desktop (or Docker Engine + Compose), ~4 GB free disk for Neo4j + FastAPI clone after index.

---

## 1. Clone and configure

```bash
git clone git@github.com:Himanshu00Singhal/opsly-assgn.git
cd opsly-assgn
cp .env.example .env
```

Edit `.env`:

| Variable | Docker Compose (recommended) | Notes |
|----------|----------------------------|--------|
| `NEO4J_PASSWORD` | Any strong password | Must match Compose Neo4j auth |
| `NEO4J_URI` | **Remove or comment** — Compose sets `bolt://neo4j:7687` inside containers | Do not point Compose at Aura unless you know what you are doing |
| `GROQ_API_KEY` | Optional | Better prose; without it, rule-based routing + templates still work |

For local-only secrets you can run `scripts/bootstrap_env.sh` if you have a **local** `keys.txt` (never commit it).

---

## 2. Start all services

```bash
docker compose up --build -d
```

Wait ~30–60 seconds, then check health:

```bash
curl -s http://localhost:8000/api/agents/health | python3 -m json.tool
```

Expect `"status": "ok"` and all five agents `"up"` plus `"neo4j": "up"`.

If agents are `"down"`, rebuild: `docker compose up --build -d` (see [docs/ENGINEERING_GUIDE.md](docs/ENGINEERING_GUIDE.md) §13 for MCP fixes).

---

## 3. Index the FastAPI repository (first time only)

```bash
curl -s -X POST http://localhost:8000/api/index \
  -H "Content-Type: application/json" \
  -d '{"mode":"full"}' | python3 -m json.tool
```

Copy the **`job_id`** from the response (a UUID). Poll until completed:

```bash
curl -s "http://localhost:8000/api/index/status/YOUR_JOB_ID_HERE" | python3 -m json.tool
```

Confirm the graph has data:

```bash
curl -s http://localhost:8000/api/graph/statistics | python3 -m json.tool
```

You should see **thousands** of nodes after a full index. The clone lives at `data/repos/fastapi/` (local only, not in git).

**Time:** First full index can take several minutes.

---

## 4. Ask questions (chat API)

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","message":"Show me the docstring for the Depends function"}' \
  | python3 -m json.tool
```

**Good demo questions:**

| Message | What it proves |
|---------|----------------|
| `Show me the docstring for the Depends function` | Graph + code analyst; answer cites `fastapi/param_functions.py` |
| `What is the FastAPI class?` | Class lookup + snippet |
| `Compare Path and Query parameters in FastAPI` | Compare intent + multiple entities |

Inspect **`meta.steps`** (orchestrator tools) and **`meta.agent_outputs`** (graph + snippet) to show multi-agent flow.

**Same session, follow-up:** reuse `"session_id"` — history is stored in the Memory agent (SQLite under `data/memory/`).

**WebSocket:** connect to `ws://localhost:8000/ws/chat`, send `{"session_id":"demo","message":"..."}`.

**Streaming HTTP:** add `"stream": true` to the chat JSON body.

---

## 5. Run unit tests (optional, local Python)

```bash
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest tests/unit -q
```

Preflight checks: open `notebooks/00_requirements_check.ipynb` (Jupyter) or import `opsly.preflight`.

---

## 6. Stop and clean up

```bash
docker compose down          # keep Neo4j volume
docker compose down -v       # also delete Neo4j data volume
```

---

## Ports reference

| Service | Port |
|---------|------|
| Gateway (API) | 8000 |
| Orchestrator MCP | 9001 |
| Indexer MCP | 9002 |
| Graph Query MCP | 9003 |
| Code Analyst MCP | 9004 |
| Memory MCP | 9005 |
| Neo4j Browser | 7474 |
| Neo4j Bolt | 7687 |

---

## What not to commit

Already in `.gitignore`: `.env`, `keys.txt`, `.venv`, `data/repos/`, `data/memory/*.db`, coverage caches.

---

## More documentation

| File | Purpose |
|------|---------|
| [README.md](README.md) | Architecture summary |
| [ass.md](ass.md) | Assignment specification |
| [docs/ENGINEERING_GUIDE.md](docs/ENGINEERING_GUIDE.md) | Deep dive: design, examples, troubleshooting |

---

## Submission checklist

- [ ] `docker compose up --build` succeeds on a clean machine
- [ ] Health endpoint all green
- [ ] Full index completed; graph statistics non-zero
- [ ] Chat returns grounded answer for `Depends` docstring
- [ ] Repo pushed without secrets (no `.env`, no `keys.txt`, no `data/repos/fastapi`)

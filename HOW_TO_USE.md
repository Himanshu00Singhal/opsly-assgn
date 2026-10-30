# How to run opsly-assgn

FastAPI take-home: five MCP agents, Neo4j graph, gateway on port 8000. Tested on **Docker Desktop (Mac)** with Python **3.12** for unit tests.

Need Docker + a few GB free once the FastAPI repo is cloned under `data/repos/`.

---

## Setup

```bash
git clone git@github.com:Himanshu00Singhal/opsly-assgn.git
cd opsly-assgn
cp .env.example .env
```

For Compose, set **`NEO4J_PASSWORD`** in `.env` (default `changeme` in the example is fine for local). Leave **`NEO4J_URI`** empty — containers talk to `bolt://neo4j:7687` on the compose network.

`GROQ_API_KEY` is optional. Without it I still get answers via regex routing + markdown templates (Groq just reads nicer on compare/explain questions).

If you keep secrets in `keys.txt` locally: `scripts/bootstrap_env.sh` writes `.env` — never commit either file.

---

## Start stack

```bash
docker compose up --build -d
```

Give Neo4j ~30s on first boot, then:

```bash
curl -s http://localhost:8000/api/agents/health | python3 -m json.tool
```

All agents + `neo4j` should show `"up"`. If not, `docker compose up --build -d` again (MCP client had to match the SDK stream shape — details in `docs/ENGINEERING_GUIDE.md`).

Quick smoke test without reading docs:

```bash
./scripts/dry_run.sh
```

---

## Index FastAPI (first time)

```bash
curl -s -X POST http://localhost:8000/api/index \
  -H "Content-Type: application/json" \
  -d '{"mode":"full"}' | python3 -m json.tool
```

Use the returned **`job_id`** (UUID), not the literal text `YOUR_JOB_ID`:

```bash
curl -s "http://localhost:8000/api/index/status/<job_id>" | python3 -m json.tool
```

When `status` is `completed`:

```bash
curl -s http://localhost:8000/api/graph/statistics | python3 -m json.tool
```

Expect thousands of nodes. Clone lands in `data/repos/fastapi/` (gitignored). Full index takes a while — go make coffee.

Incremental re-run: same POST with `"mode":"incremental"`.

---

## Chat

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","message":"Show me the docstring for the Depends function"}' \
  | python3 -m json.tool
```

Good demo prompts I used:

- `Show me the docstring for the Depends function` → should mention `fastapi/param_functions.py`
- `What is the FastAPI class?`
- `Compare Path and Query parameters in FastAPI`

Open **`meta.steps`** in the JSON if you need to show orchestrator + parallel agents for the rubric. **`meta.agent_outputs`** has the raw graph hits and snippet.

Same **`session_id`** keeps history in SQLite (`data/memory/`). WebSocket: `ws://localhost:8000/ws/chat`. SSE: add `"stream": true` to the POST body.

---

## Tests (local venv)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit -q
```

---

## Stop

```bash
docker compose down      # keeps neo4j volume
docker compose down -v   # wipes graph volume
```

---

## Ports

| What | Port |
|------|------|
| Gateway | 8000 |
| Orchestrator | 9001 |
| Indexer | 9002 |
| Graph query | 9003 |
| Code analyst | 9004 |
| Memory | 9005 |
| Neo4j browser / bolt | 7474 / 7687 |

---

## Docs

- `README.md` — diagram + one-liner
- `ass.md` — spec from the assignment
- `docs/ENGINEERING_GUIDE.md` — how I wired it, bugs I hit, curl examples

Before push: no `.env`, no `keys.txt`, no `data/repos/fastapi` in git.

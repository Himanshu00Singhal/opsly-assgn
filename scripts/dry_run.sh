#!/usr/bin/env bash
# Smoke test after `docker compose up` (and ideally after index finished).
set -euo pipefail
BASE="${GATEWAY_URL:-http://localhost:8000}"

echo "== health =="
health="$(curl -sf "${BASE}/api/agents/health")"
echo "$health" | python3 -m json.tool
echo "$health" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('status')=='ok', d"

echo ""
echo "== graph stats (skip if zero — run index first) =="
curl -sf "${BASE}/api/graph/statistics" | python3 -m json.tool | head -20

echo ""
echo "== chat: Depends docstring =="
out="$(curl -sf -X POST "${BASE}/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"dry-run-script","message":"Show me the docstring for the Depends function"}')"
echo "$out" | python3 -c "
import json, sys
d = json.load(sys.stdin)
r = d.get('response', '')
assert 'Depends' in r and 'param_functions' in r, r[:500]
assert len(d.get('meta', {}).get('steps', [])) >= 3
print('ok — grounded Depends answer, orchestrator steps present')
print(r[:280] + ('...' if len(r) > 280 else ''))
"

echo ""
echo "dry_run finished"

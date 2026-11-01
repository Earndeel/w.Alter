#!/usr/bin/env bash
# Post-repair smoke test for the W.Alter/Hermes memory stack.
# Validated live on 2026-08-21 after the qdrant-client venv incident.
#
# Usage: bash post_repair_smoke_test.sh [--write-test]
#   --write-test  also performs a write->recall round-trip (inserts ONE test fact)
# Default: read-only. Exit 0 = all pass, 1 = at least one failure.
set -u
FAIL=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; FAIL=1; }

check_health() {
  local port name body
  for spec in "8888:hindsight-api" "8889:hybrid-search" "8890:write-worker" "8891:gateway"; do
    port="${spec%%:*}"; name="${spec##*:}"
    body=$(curl -s -m 5 "http://127.0.0.1:${port}/health" || true)
    if echo "$body" | grep -qE '"status":"(healthy|ok)"'; then
      ok "$name :$port healthy"
    else
      bad "$name :$port -> ${body:-no response}"
    fi
  done
}

check_qdrant() {
  local n
  n=$(curl -s -m 5 http://127.0.0.1:6333/collections/memories \
    | python3 -c "import json,sys;print(json.load(sys.stdin)['result'].get('points_count',-1))" 2>/dev/null || echo -1)
  if [ "$n" -gt 0 ]; then ok "qdrant memories points=$n"; else bad "qdrant memories points=$n"; fi
}

check_pg_activity() {
  local rows
  rows=$(docker exec hindsight-pg psql -U hindsight -d hindsight -t -A -c \
    "SELECT COUNT(*) FROM memory_units WHERE created_at > NOW() - INTERVAL '7 days';" 2>/dev/null || echo 0)
  if [ "$rows" -gt 0 ]; then
    ok "pg memory_units created last 7d = $rows"
  else
    bad "pg memory_units inactive 7d = $rows (write path dead?)"
  fi
}

roundtrip() {
  # Real contracts (verified 2026-08-21):
  #   write:  POST /v1/default/banks/{bank}/memories   {"items":[{"content": "..."}]}
  #   recall: POST /v1/default/banks/{bank}/memories/recall {"query":..., "max_tokens":N}
  local ts hit
  ts=$(date +%s)
  curl -s -m 15 -X POST http://127.0.0.1:8888/v1/default/banks/walter/memories \
    -H 'Content-Type: application/json' \
    -d "{\"items\":[{\"content\":\"SMOKE TEST $ts: round-trip probe written by post_repair_smoke_test.sh.\"}]}" \
    | grep -q '"success":true' && ok "write accepted" || { bad "write rejected"; return; }
  sleep 40   # extraction is async (worker polls ~30s)
  hit=$(curl -s -m 25 -X POST http://127.0.0.1:8888/v1/default/banks/walter/memories/recall \
    -H 'Content-Type: application/json' \
    -d "{\"query\":\"SMOKE TEST $ts round-trip probe\",\"max_tokens\":300}" \
    | grep -c "SMOKE TEST $ts" || true)
  if [ "${hit:-0}" -ge 1 ]; then ok "recall round-trip (8888)"; else bad "recall round-trip: test fact not retrieved"; fi
}

check_health
check_qdrant
check_pg_activity
[ "${1:-}" = "--write-test" ] && roundtrip

echo "---"
if [ "$FAIL" -eq 0 ]; then echo "ALL PASS"; else echo "FAILURES PRESENT"; fi
exit $FAIL

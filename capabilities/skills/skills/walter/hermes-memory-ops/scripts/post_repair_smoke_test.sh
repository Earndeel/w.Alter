#!/usr/bin/env bash
# Post-repair smoke test of Walter Memory (rewritten 2026-11-09: the former version tested the retired Hindsight /
# Qdrant / write-worker stack). Read-only. Exit 0 = all pass, 1 = at least one failure. Prints counts, never content.
set -u
FAIL=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; FAIL=1; }

for u in walter-memory-gateway walter-logs-watch raw-vault-s3; do
  systemctl is-active --quiet "$u" && ok "$u active" || bad "$u not active"
done

h=$(timeout 120 walter-memory health 2>/dev/null)
if echo "$h" | python3 -c 'import json,sys; sys.exit(0 if isinstance(json.load(sys.stdin).get("problems"), list) else 1)' 2>/dev/null; then
  ok "walter-memory health answers ($(echo "$h" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["problems"]))') problem(s))"
else
  bad "walter-memory health does not answer"
fi

n=$(timeout 60 walter-memory search "sauvegarde" --limit 5 2>/dev/null | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)
[ "${n:-0}" -gt 0 ] && ok "unified search (FTS + vectors) returns $n" || bad "unified search returns nothing"

ext=$(docker exec hindsight-pg psql -U hindsight -d hindsight -Atc \
  "select count(*) from pg_extension where extname in ('vector','pg_trgm','pgcrypto','unaccent')" 2>/dev/null || echo 0)
[ "$ext" = 4 ] && ok "extensions vector, pg_trgm, pgcrypto, unaccent present" || bad "extensions missing ($ext/4)"

recent=$(docker exec hindsight-pg psql -U hindsight -d hindsight -Atc \
  "select count(*) from core.events where ingested_at > now() - interval '1 day'" 2>/dev/null || echo 0)
[ "${recent:-0}" -gt 0 ] && ok "core.events ingested in the last 24 h = $recent" || bad "no core.events in the last 24 h"

exit $FAIL

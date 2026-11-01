# Hindsight Memory Full Stack Audit Checklist

Run when asked to audit the memory system end-to-end. Execute checks in parallel where possible.

## Step 1: Infrastructure health

```bash
curl -s http://127.0.0.1:8888/health          # Hindsight API
curl -s http://127.0.0.1:8889/health          # Hybrid Search (read path)
curl -s http://127.0.0.1:8890/health          # Write Worker

docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -i "hindsight\|qdrant"
docker inspect --format '{{.Name}}: restarts={{.RestartCount}}' hindsight-pg qdrant
```

## Step 2: Data volume + duplicates

```bash
# PG stats (via Docker — psql not on host)
docker exec hindsight-pg psql -U hindsight -d hindsight -t -c "SELECT count(*) FROM memory_units;"
docker exec hindsight-pg psql -U hindsight -d hindsight -t -c "SELECT count(*) FROM memory_links;"
docker exec hindsight-pg psql -U hindsight -d hindsight -t -c "SELECT pg_size_pretty(pg_database_size('hindsight'));"

# Exact duplicates — use md5(text), NOT norm_text (column doesn't exist)
docker exec hindsight-pg psql -U hindsight -d hindsight -t -c "
SELECT count(*) as dup_groups, sum(cnt)-count(*) as excess
FROM (SELECT md5(text), count(*) as cnt FROM memory_units GROUP BY md5(text) HAVING count(*) > 1) sub;"

# Units by age
docker exec hindsight-pg psql -U hindsight -d hindsight -t -c "
SELECT CASE WHEN created_at > now()-interval '1 day' THEN '24h'
  WHEN created_at > now()-interval '7 days' THEN '7d'
  WHEN created_at > now()-interval '30 days' THEN '30d'
  ELSE 'older' END, count(*) FROM memory_units GROUP BY 1 ORDER BY 2 DESC;"

# Qdrant collection counts
curl -s http://127.0.0.1:6333/collections/memories | python3 -c "import json,sys; print('memories:', json.load(sys.stdin)['result']['points_count'])"
curl -s http://127.0.0.1:6333/collections/entities | python3 -c "import json,sys; print('entities:', json.load(sys.stdin)['result']['points_count'])"
```

## Step 3: Systemd timers (memory-related)

```bash
for t in dream-cycle memory-guarded-maintenance memory-autopilot hindsight-stack-check; do
  echo "--- $t ---"
  systemctl status ${t}.service 2>&1 | head -8
done
```

## Step 4: Cron jobs

Use `cronjob action=list`. Check `last_status` for each — `"error"` usually means provider cascade failure (both primary + fallback unreachable).

## Step 5: Script syntax validation

After finding corruption (redaction tools truncating `os.getenv()` calls), check all memory scripts:

```bash
for f in /root/.hermes/services/dream_cycle.py \
         /root/.hermes/scripts/memory_dreaming.py \
         /root/.hermes/scripts/memory_connectors.py \
         /root/.hermes/scripts/hindsight_pg_exact_dedup.py; do
  python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>&1 && echo "OK: $f" || echo "FAIL: $f"
done

# Find corrupted os.getenv calls
grep -rn 'os\.get\.\.\.' /root/.hermes/scripts/ /root/.hermes/services/
```

## Step 6: Latest run outputs

```bash
cat /root/.hermes/logs/hindsight-stack-check-latest.json | python3 -m json.tool
cat /root/.hermes/logs/memory-autopilot/latest.json | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('score:', d.get('summary',{}).get('score'))
print('warnings:', d.get('summary',{}).get('warnings'))
print('drift:', d.get('derived',{}).get('pg_qdrant_drift_interpretation'))
"
cat /root/.hermes/logs/memory-autopilot/pg-exact-dedup-latest.json | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(f'ok={d.get(\"ok\")} blocked={d.get(\"blocked\")} planned={d.get(\"planned_delete_units\")} max={d.get(\"max_delete\")}')
"
```

## Interpreting PG vs Qdrant drift

PG keeps the full history (7000+ units), Qdrant keeps the active recall set (~270). This is by design — PG is the source of truth, Qdrant is the fast search index. A ratio of 20-30x is expected. The autopilot tracks this as `pg_to_qdrant_memory_ratio`.

**Normal:** PG >> Qdrant (broad history vs active index)
**Bad:** Qdrant > PG (data corruption) or Qdrant = 0 (migration failure)

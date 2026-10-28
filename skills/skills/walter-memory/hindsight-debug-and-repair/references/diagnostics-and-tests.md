## Diagnostic Checklist

```bash
# 1. Check if API is running
curl -s http://127.0.0.1:8888/health
ss -tlnp | grep 8888

# 2. Check PG container
docker ps | grep hindsight-pg
docker exec hindsight-pg psql -U hindsight -d hindsight -c "SELECT extname FROM pg_extension;"

# 3. Check embed log for errors
tail -30 /root/.hermes/logs/hindsight-embed.log

# 4. Check API log for errors
tail -30 /root/.hermes/logs/hindsight-api.log

# 5. Check installed packages
venv/bin/pip list | grep hindsight

# 6. Check config
cat /root/.hermes/hindsight/config.json
```

## Comprehensive Test Suite (10 tests)

### Automated Script (preferred)

```bash
# Full test suite — exit code 0 = all pass, 1 = failure
python3 /root/.hermes/scripts/test_hindsight.py

# With detailed warnings
python3 /root/.hermes/scripts/test_hindsight.py --verbose
```

The script covers all 10 tests below, auto-creates test memories, and auto-cleans them after.
Test data uses prefix `TEST_SUITE:` for easy identification.

### Manual Tests (for debugging individual components)

### Test 1: API Health
```bash
curl -s http://127.0.0.1:8888/health
# Expected: {"status":"healthy","database":"connected"}
```

### Test 2: Retain (store memories)
```bash
curl -s -X POST http://127.0.0.1:8888/v1/default/banks/walter/memories \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"content":"test fact","context":"test context"}]}'
# Expected: {"id": "...", "status": "ok"}
```

### Test 3: Recall (various query types)
Test: exact match (EN), exact match (FR), semantic, entity-based, bilingual, technical deep, vague, recent events. All should return results.

### Test 4: Consolidate
```bash
curl -s -X POST http://127.0.0.1:8888/v1/default/banks/walter/consolidate \
  -H 'Content-Type: application/json' -d '{}'
# Returns operation_id, processes asynchronously
```

### Test 5: Entities + Graph
```bash
curl -s http://127.0.0.1:8888/v1/default/banks/walter/entities
curl -s http://127.0.0.1:8888/v1/default/banks/walter/entities/graph
```

### Test 6: Performance benchmarks
Run 10 recall queries, measure P50/P95. Target: P50 < 3s.

### Test 7: Edge cases
Empty query (expect 422), single char, 500-char query, special chars, emoji, SQL injection, unicode, null bytes. All except empty should return 200.

**Edge case behavior (tested 2026-04-26):**
- Empty query `""` → HTTP 422 (validation error, correct)
- Special chars `!@#$%^&*()` → HTTP 422 (validation error)
- Emoji `🔥💧🎉` → HTTP 422 (validation error)
- SQL injection, unicode, null bytes, 500-char query → HTTP 200 (handled gracefully)

### Test 8: Plugin integration
Verify `config.json`: auto_recall=true, auto_retain=true, retain_async=true.
Check memories created in last hour: `SELECT COUNT(*) FROM memory_units WHERE created_at > NOW() - INTERVAL '1 hour';`

### Test 9: Cron readiness
Verify dreaming script syntax: `python3 -c "import ast; ast.parse(open('/root/.hermes/scripts/memory_dreaming.py').read())"`
Verify endpoints: consolidate, entities, mental-models all return HTTP 200.

### Test 10: Data integrity
```sql
-- Counts
SELECT COUNT(*) FROM memory_units;    -- memories
SELECT COUNT(*) FROM entities;         -- entities
SELECT COUNT(*) FROM unit_entities;    -- unit↔entity links
SELECT COUNT(*) FROM memory_links;     -- memory graph links
SELECT COUNT(*) FROM chunks;           -- chunks

-- Embedding coverage
SELECT COUNT(*) FROM memory_units WHERE embedding IS NOT NULL;
SELECT COUNT(*) FROM memory_units WHERE embedding IS NULL;  -- should be 0

-- Dimension check
SELECT vector_dims(embedding) FROM memory_units WHERE embedding IS NOT NULL LIMIT 1;

-- Duplicates
SELECT COUNT(*) FROM (SELECT text, COUNT(*) c FROM memory_units GROUP BY text HAVING COUNT(*) > 1) dup;

-- Similar duplicates (pg_trgm)
SELECT COUNT(DISTINCT a.id) FROM memory_units a JOIN memory_units b ON a.id < b.id AND similarity(a.text, b.text) > 0.85;

-- Extensions
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','pg_trgm');

-- DB size
SELECT pg_size_pretty(pg_database_size('hindsight'));
```

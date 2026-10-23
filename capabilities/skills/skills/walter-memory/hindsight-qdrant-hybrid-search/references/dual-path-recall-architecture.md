# Dual-Path Recall Architecture

There are TWO independent recall paths in the Hindsight stack. Knowing which one does what is critical for debugging search quality and understanding why some entries seem "missing."

## The Two Paths

### Path 1: Hindsight API (port 8888) → PostgreSQL
- Endpoint: `POST /v1/default/banks/{bank_id}/memories/recall`
- Backend: PostgreSQL `memory_units` table (embedding column)
- Scores: Always 0.000 (no proper vector similarity scoring, results ordered by recency/text match)
- Coverage: ALL entries (7,600+ as of May 2026)
- Used by: Hermes `hindsight_recall` tool

### Path 2: Hybrid Search (port 8889) → Qdrant
- Endpoint: `POST http://127.0.0.1:8889/recall`
- Backend: Qdrant `memories` collection (dense vectors, 768d cosine)
- Scores: Proper cosine similarity (0.48–0.91 typical range)
- Coverage: Only entries processed by write worker (~270 as of May 2026)
- Used by: Dream cycle health checks, Memory Sniper injection compiler

## What Goes Where

| Source | Writes to PG | Writes to Qdrant |
|---|---|---|
| Write Worker (conversation extraction) | No | Yes |
| Hindsight API `/memories` (retain) | Yes | No |
| Memory Connectors (Beeper/Telegram) | Yes (via retain API) | No |
| Dream Cycle (dedup merge) | Yes (updates) | Yes (upserts) |

## Implications

1. **Entries from connectors are PG-only** — searchable via `hindsight_recall` but won't appear in hybrid search or Memory Sniper
2. **Scores from PG recall are always 0.000** — ranking is by recency, not relevance
3. **The reconcile dry-run tracks drift** — `pg_unique_texts_absent_from_qdrant` counts PG-only entries (6,501 as of May 2026)
4. **Backfilling PG→Qdrant** would improve recall quality for historical entries but needs careful handling to avoid duplicates

## Quick Verification

```bash
# Count PG entries
docker exec hindsight-pg psql -U hindsight -d hindsight -t -c "SELECT count(*) FROM memory_units;"

# Count Qdrant entries
curl -s http://127.0.0.1:6333/collections/memories | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['points_count'])"

# Test PG-only entry (recent connector ingest)
curl -s -X POST "http://127.0.0.1:8888/v1/default/banks/walter/memories/recall" \
  -H "Content-Type: application/json" \
  -d '{"query": "Lucas Thai Bangkok", "limit": 3}'
# → Returns results with score=0.000

# Same query on hybrid search
curl -s -X POST "http://127.0.0.1:8889/recall" \
  -H "Content-Type: application/json" \
  -d '{"query": "Lucas Thai Bangkok", "limit": 3}'
# → Returns fewer/no results (not in Qdrant)
```

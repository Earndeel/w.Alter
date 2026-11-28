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

## PG↔Qdrant Sync (Jarvis Memory System)

The PG↔Qdrant drift problem (entries added via retain API go to PG only, not Qdrant) has been solved by the Jarvis Memory System:

- **Sync Worker**: `/root/.hermes/services/jarvis/pg_qdrant_sync_worker.py`
  - `--dry-run`: show what would be synced
  - `--sample-run --limit N`: sync N entries
  - `--full-run`: complete backfill
  - `--incremental`: process outbox only
  - `--health`: sync health check

- **Memory Gateway**: `/root/.hermes/services/jarvis/memory_gateway.py` (port 8891)
  - Single access point for all agents
  - `/recall/fast` (Qdrant only, <800ms)
  - `/recall/balanced` (Qdrant+PG, <1500ms)
  - `/recall/deep` (PG full, <5000ms)

- **Outbox pattern**: New facts get `memory_outbox` entries → sync worker processes them → Qdrant updated

- **Full backfill performance**: ~500 entries/5.5min (Gemini Embedding 2, free tier). 7,692 entries ≈ 1.5h.

See `jarvis-memory-system` skill for full architecture.

## Dual-Path Recall Architecture

There are TWO independent recall paths — knowing which one does what is critical for debugging search quality:

| Path | Port | Backend | Scores | Coverage |
|---|---|---|---|
| Hindsight API `/memories/recall` | 8888 | PostgreSQL (embedding column) | Often weak/0.000 or text/recency-biased depending API version | Broad PG history |
| Hybrid Search `/recall` | 8889 | Qdrant (dense vectors) + reranker | Proper cosine/rerank scores | Only entries synced/vectorized into Qdrant |

Hermes' Hindsight plugin reads `~/.hermes/hindsight/config.json`. If `api_url` is `http://127.0.0.1:8888`, both auto-recall prefetch and the `hindsight_recall` tool call port 8888 (Hindsight API → PG). This means broad coverage but noisier ranking and potentially verbose context injection.

**Important terminology pitfall**: plugin `memory_mode: "hybrid"` does **not** mean PG+Qdrant hybrid search. In the plugin it means "auto context injection + tools enabled". The Qdrant hybrid-search service on port 8889 is separate and is not used unless the plugin/client is explicitly routed through it or a gateway layer calls it.

The dream cycle health checks, Memory Sniper, and direct hybrid-search probes use port 8889 (Hybrid Search → Qdrant), which has proper vector/reranker scoring but only covers entries processed by the write worker/sync pipeline.

**Implication**: Entries added via the retain API (connectors, manual retain) may land in PG before Qdrant. They are searchable via `hindsight_recall` on 8888 but may not appear in hybrid search or Memory Sniper until sync/reconcile processes them. The reconcile dry-run tracks this drift (`pg_unique_texts_absent_from_qdrant`).

### Debug checklist for "why did Hindsight inject so much/noisy context?"

1. Read `~/.hermes/hindsight/config.json` and check `api_url`, `memory_mode`, `recall_budget`, `auto_recall`, and `recall_prefetch_method`.
2. If `api_url` points to 8888, expect PG recall behavior, not Qdrant hybrid ranking.
3. Compare counts: PG `memory_units` vs Qdrant `/collections/memories` or `hybrid-search /health` `memories_count`.
4. Lower `recall_budget` or route auto-recall through 8889/Memory Gateway if injection is too verbose; use PG as deep fallback.

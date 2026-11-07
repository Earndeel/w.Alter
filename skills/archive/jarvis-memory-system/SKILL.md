---
name: jarvis-memory-system
description: Jarvis organic memory system for W.Alter — PG as truth, Qdrant as derived index, Memory Gateway, Action Firewall, Context Builder, Belief Engine.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [memory, jarvis, pg, qdrant, gateway, firewall]
---

# Jarvis Memory System

**User-facing name:** W.Alter Memory. “Jarvis” is an internal/legacy codename only; do not present it as a separate assistant or persona. Monsieur explicitly corrected this: it is supposed to be W.Alter’s memory.

Organic memory architecture for W.Alter. PostgreSQL = source of truth, Qdrant = fast derived index.

**Naming**: This system is "W.Alter memory" in user-facing contexts. "Jarvis" is an internal build codename — never present it to the user as "Jarvis".

## Architecture

```
Sources → Data Ingestion → memory_events → Extraction → memory_facts
    → Memory Gateway (8891) → Context Builder (8893) → Actors
    → Action Firewall (8892) → Tools
```

## Ports & Services

| Service | Port | Purpose |
|---|---|---|
| hindsight-api | 8888 | Hindsight API (PG-backed) |
| hybrid-search | 8889 | Qdrant search + ZeRank-2 reranker |
| write-worker | 8890 | Real-time memory extraction (fired events) |
| jarvis-memory-gateway | 8891 | Single memory access point (4 recall modes) |
| jarvis-action-firewall | 8892 | Action risk evaluation (0-4 scale) |
| jarvis-context-builder | 8893 | Context packs per actor (gemini_live, mimo, hermes) |
| jarvis-belief-preference-engine | 8894 | Living model of user (beliefs, preferences, rules) |
| jarvis-local-embed | 8896 | Local embedding service (all-MiniLM-L6-v2, 384d) |
| jarvis-style-resolver | 8895 | Response style adapter (8 task types) |

## Recall Modes

| Mode | Latency | Pipeline | Actor | Use Case |
|---|---|---|---|---|
| /recall/ultra | <50ms | Local embedding (384d) + Qdrant memories_local | Gemini Live / Voice | Real-time voice conversations |
| /recall/fast | <800ms | Gemini Embedding API + Qdrant | Gemini Live (fallback) | When local fails |
| /recall/balanced | <1500ms | Qdrant + PG keyword + FlashRank | Hermes | Written analysis |
| /recall/deep | <5000ms | Hindsight API + PG + ZeRank-2 | MiMo | Deep reasoning |

## Local Embedding (Voice Recall)

**Model:** all-MiniLM-L6-v2 (sentence-transformers, 22M params, 80MB RAM)
**Dimensions:** 384d (separate Qdrant collection `memories_local`)
**Latency:** ~11ms per embedding on CPU, ~35-40ms end-to-end with Qdrant search
**Quality:** ~80% relevance vs Gemini Embedding 2 (acceptable for voice)

**Why separate collection:** Different embedding models occupy different vector spaces. Gemini 768d and MiniLM 384d cannot be searched together — cosine similarity is meaningless across models. Each needs its own Qdrant collection.

**Backfill:** `pg_qdrant_sync_worker.py` handles both collections. Local backfill runs at ~56 facts/sec (CPU).

**Fallback chain:** local (8896) → Gemini Embedding API (8889) → PG keyword search

- Schema: `/root/.hermes/services/jarvis/001_organic_memory_schema.sql`
- Gateway: `/root/.hermes/services/jarvis/memory_gateway.py`
- Firewall: `/root/.hermes/services/jarvis/action_firewall.py`
- Context: `/root/.hermes/services/jarvis/context_builder.py`
- Beliefs: `/root/.hermes/services/jarvis/belief_preference_engine.py`
- Sync: `/root/.hermes/services/jarvis/pg_qdrant_sync_worker.py`
- Local Embed: `/root/.hermes/services/jarvis/local_embedding_service.py`
- Style: `/root/.hermes/services/jarvis/response_style_resolver.py`

## Voice Recall — 3-Layer Strategy (recall/ultra)

For Gemini Live speech-to-speech, memory must be <50ms. Three layers:

1. **Pre-load** (0ms during call): Context Builder loads ~2000 tokens at call start
2. **Cache** (<5ms): LRU cache for frequent queries in Memory Gateway
3. **Local embedding** (~35ms): all-MiniLM-L6-v2 (384d) → Qdrant memories_local

Pipeline: `query → sentence-transformers (11ms) → Qdrant memories_local (30ms) → format (5ms) = ~35ms`

Use `/recall/ultra` for voice. Falls back to `/recall/fast` if local embedding fails.

### Key: Two Separate Qdrant Collections

| Collection | Dimensions | Embedding Model | Use Case |
|---|---|---|---|
| memories | 768d | Gemini Embedding 2 | Quality recall (balanced/deep) |
| memories_local | 384d | all-MiniLM-L6-v2 | Voice recall (ultra) |

**NEVER mix vectors from different embedding models** — cosine similarity is meaningless across embedding spaces. Each collection must use vectors from ONE model only.

## Memory Gateway Endpoints

- POST /recall/ultra — local embedding + Qdrant, <50ms (voice/Gemini Live)
- POST /recall/fast — Gemini Embedding + Qdrant, <800ms (fallback)
- POST /recall/balanced — Qdrant+PG, <1500ms (Hermes)
- POST /recall/deep — PG full, <5000ms (MiMo)
- POST /retain/candidate — uncertain fact
- POST /retain/confirmed — active canonical fact
- POST /belief/update — update current belief
- POST /invalidate — controlled invalidation
- GET /user/state — current state of Lucas
- GET /health/full — detailed health with drift

## Action Firewall Risk Levels

- 0: Read-only
- 1: Suggestion/draft
- 2: Low-risk reversible
- 3: Sensitive (requires confirmation)
- 4: Forbidden without special procedure

## PG→Qdrant Sync

```bash
python3 /root/.hermes/services/jarvis/pg_qdrant_sync_worker.py --dry-run
python3 /root/.hermes/services/jarvis/pg_qdrant_sync_worker.py --sample-run --limit 100
python3 /root/.hermes/services/jarvis/pg_qdrant_sync_worker.py --full-run
python3 /root/.hermes/services/jarvis/pg_qdrant_sync_worker.py --incremental
python3 /root/.hermes/services/jarvis/pg_qdrant_sync_worker.py --health
```

Production hardening applied 2026-05-22:
- `memory_facts` has `fact_key`, `value_hash`, `expires_at`, `last_seen_at`.
- `memory_facts_outbox_aiu` trigger enqueues create/update/delete events into `memory_outbox`.
- `expire_stale_memory_facts()` auto-expires active facts whose `expires_at` passed.
- `write_worker.py` writes facts to PostgreSQL first; it no longer creates direct UUID4 Qdrant points.
- `pg_qdrant_sync_worker.py` is the only Qdrant writer for memory facts; Qdrant point IDs are deterministic UUIDs derived from PG fact IDs.
- `pg-qdrant-sync.timer` runs every ~2 minutes for incremental outbox processing.
- Supersession rule: same `fact_key` + different `value_hash` marks old fact `superseded/canonical=false/valid_until=now`, inserts a new active canonical fact, deletes old Qdrant point, syncs new point.
- Qdrant indexes only active canonical non-expired facts; PG keeps the full history.

## Voice-First Recall (recall/ultra)

Local embedding model: all-MiniLM-L6-v2 (384d, ~11ms/query, sentence-transformers)
Qdrant collection: `memories_local` (384d, Cosine)
Service: jarvis-local-embed (port 8896)
Avg latency: 28-40ms (vs 700-850ms for Gemini Embedding API)
Quality: ~80% relevance (vs ~95% for Gemini API)
Trade-off: 15% quality loss for 20x speed gain — acceptable for voice.

Three-layer strategy for Gemini Live:
1. Pre-load context at conversation start (~2000 tokens, 0ms during call)
2. LRU cache for frequent queries (<5ms)
3. Local embedding + Qdrant for new queries (~40ms)

## Voice Router Integration

The voice_router (port 12110) uses Memory Gateway ultra as primary recall for voice conversations.

**Flow:** Gemini Live → voice_router → `/recall/ultra` (local, <50ms) → fallback to Hindsight `/recall` (Gemini API)

**Changes in voice_router_service.py:**
- Added `MEMORY_GATEWAY_ULTRA_URL` env var (default: `http://127.0.0.1:8891/recall/ultra`)
- `hindsight_context_lookup()` tries ultra first (2s timeout), falls back to Hindsight hybrid search
- Response includes `data.source: "memory_gateway_ultra"` or `"hindsight_fallback"`

**Restart after changes:** `systemctl restart voice-router voice-call`

**Critical:** After restarting voice-call server, browser WebSocket state becomes stale. User MUST hard-refresh the page (Ctrl+Shift+R) to reconnect.

- See `references/voice-router-memory-integration.md` for full details

## Pitfalls (quick ref — see references/pitfalls-discovered.md for full detail)

- **PG Docker IP**: From host Python scripts, connect via `172.17.0.4` (Docker internal IP), NOT `localhost`. No port binding to host. Use `docker inspect hindsight-pg --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'` to verify.
- Embedding must use `outputDimensionality: 768` (Gemini returns 3072 by default)
- Python 3.11: no backslashes in f-string expressions
- memory_facts uses `content` not `text`
- Full backfill: ~500 entries/5.5min, run in batches via foreground calls
- background=true + pipe to tee fails — use wrapper script with `exec > file 2>&1`
- **Qdrant named vectors API**: search format is `{"name": "dense", "vector": vec}`, NOT `{"dense": vec}`. Also, `/points/search` uses `{"vector": ...}` while `/points/query` uses `{"query": ...}` — different endpoints, different formats. Qdrant 1.17.1.
- **Qdrant indexed_vectors_count=0 is normal after upsert** — HNSW index builds asynchronously. Search still works on unindexed segments.
- **NEVER mix embedding models in same collection** — cosine similarity meaningless across spaces. Use separate collections (memories=768d Gemini, memories_local=384d MiniLM). Padding 384d→768d with zeros does NOT work when the other vectors are from a different model.
- **Qdrant search vs query**: `/points/search` uses `{"vector": ...}`, `/points/query` uses `{"query": ...}` — different endpoints, different formats
- **NEVER mix embedding models in same collection** — cosine similarity meaningless across spaces. Use separate collections (memories=768d Gemini, memories_local=384d MiniLM)
- **Local embedding backfill**: 7,692 facts in ~136s (56/s) on CPU. Use batch_size=100.
- **Gemini API spending cap** blocks Write Worker, Dream Cycle, and hybrid search (Gemini Embedding). When cap is hit, all Gemini-dependent services return 429 or 500. Fix: https://ai.studio/spend. The local embedding pipeline (recall/ultra) continues working since it doesn't use Gemini API.

## Performance Benchmarks (2026-05-19)

Note: Lucas wants "Jarvis" renamed conceptually to "W.Alter Memory" — it's W.Alter's memory system, not a separate character.

| Mode | Avg Latency | P50 | P90 | Target | Notes |
|---|---|---|---|---|---|
| recall/ultra (voice) | ~28ms | 36ms | 47ms | <50ms | local embedding, cache hits 0-1ms |
| recall/fast | ~126ms | 139ms | 150ms | <800ms | Gemini Embedding API |
| recall/balanced | ~780ms | - | - | <1500ms | Qdrant+PG |
| recall/deep | ~2230ms | - | - | <5000ms | PG full |
| Local embedding direct | ~11ms | - | - | - | all-MiniLM-L6-v2 CPU |

## Full Backfill Commands

```bash
# Batch of 500 (~5.5 min)
python3 -c "import sys; sys.path.insert(0, '/root/.hermes/services/jarvis'); from pg_qdrant_sync_worker import full_run; print(full_run(limit=500))"

# Check progress
docker exec hindsight-pg psql -U hindsight -d hindsight -t -c "SELECT qdrant_sync_status, count(*) FROM memory_facts GROUP BY 1;"
curl -s http://127.0.0.1:6333/collections/memories | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['points_count'])"
```

## Files

- `references/pitfalls-discovered.md` — all pitfalls from the build session
- `references/voice-recall-architecture.md` — 3-layer voice recall strategy, Qdrant named vectors API
- `templates/jarvis-local-embed.service` — systemd unit for local embedding service
- `scripts/backfill_local_embeddings.py` — backfill memories_local with local embeddings

## Additional Services

| Service | Port | Purpose |
|---|---|---|
| jarvis-style-resolver | 8895 | Response style adapter (8 task types) |
| jarvis-local-embed | 8896 | Local embedding service (all-MiniLM-L6-v2, 384d) |

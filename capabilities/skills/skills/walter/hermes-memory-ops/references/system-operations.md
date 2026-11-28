---
name: memory-system-operations
description: Operational knowledge for W.Alter memory stack — cron routing, health watchdogs, sync timers, backfill, Memory Gateway, and troubleshooting patterns.
triggers:
  - Memory system health check or audit
  - Cron jobs failing silently
  - PG↔Qdrant drift investigation
  - Memory ingestion stopped or stale
  - memories_local backfill needed
  - Memory Gateway recall/ultra debugging
  - Voice recall latency investigation
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [memory, operations, watchdog, maintenance, qdrant, sync]
---

# Memory System Operations

Operational runbook for W.Alter's memory stack. For architecture details, see `jarvis-memory-system` and `hindsight-qdrant-hybrid-search` skills.

## Service Map (ports)

| Service | Port | Model Used | Purpose |
|---|---|---|---|
| hindsight-api | 8888 | Gemini Flash Lite (extraction) | Retain, consolidate |
| hybrid-search | 8889 | Gemini Embed 2 + ZeRank-2 | Semantic recall |
| write-worker | 8890 | Gemini Flash Lite (free) | Fact extraction |
| memory-gateway | 8891 | None (routing only) | Unified recall API |
| local-embed | 8896 | all-MiniLM-L6-v2 (CPU) | Voice recall embedding |
| voice-router | 12110 | None (routing) | Gemini Live proxy |

## Health Watchdog

Script: `~/.hermes/scripts/memory_health_check.sh`
Cron: every 5 min, no_agent, delivers to Telegram only on failure.
Cost: $0/month (pure bash, no LLM).

Checks: all 6 services + Qdrant + PG + systemd + drift (768d and 384d).
Pattern: silent when healthy (watchdog pattern). Auto-restarts dead services.

### Handling Noisy Alerts ("Stop reminder")
When the watchdog is unhealthy, it may trigger frequent, repetitive Telegram warnings. If Monsieur sends a stop instruction (e.g., "Stop reminder", "arrête les alertes" or similar):
1. **Do not ignore or argue.** Identify the active watchdog cron job immediately using `cronjob(action='list')`.
2. **Pause the job:** Use `cronjob(action='pause', job_id='<id>')` to silence the failing watchdog.
3. **Confirm in 1 sentence:** State clearly that the "Memory Health Check" (or the specific alert job) has been successfully paused.
4. **Follow-up:** Check the health status afterwards when Monsieur isn't actively waiting, or suggest checking once the root database or service issue is investigated.

## Sync Timers

| Timer | Freq | What | Cost |
|---|---|---|---|
| pg-qdrant-sync.timer | 2 min | PG → Qdrant 768d (outbox) | $0 (embedding already in PG) |
| memories-local-sync.timer | 5 min | PG → Qdrant 384d (MiniLM) | $0 (local CPU embed) |

## Cron Jobs (LLM-powered)

All use `kie/gemini-3.5-flash`. Total cost ~$0.80/month.

- Memory Dreaming (daily 4h) — consolidation, dedup
- Memory External Connectors (daily 5h) — ingest Telegram/Beeper
- Skill Intelligence Loop (daily 3h) — skill gap analysis
- AI Free Offers Watchdog (daily midnight) — model deals
- Location Insights (every 6h) — GPS data processing

## Critical Pitfalls

### 1. Cron provider inheritance (silent death)

Cron jobs with `model=null / provider=null` inherit the system default. If `fallback_providers` points to a depleted provider (e.g., OpenRouter $0 credits), ALL crons fail silently every night. This went undetected for **13 days** in production (2026-05-25 to 2026-06-07).

**Fix:** Always set explicit `model` + `provider` on each cron job:
```
cronjob action=update job_id=X model={"model": "gemini-3.5-flash", "provider": "kie"}
```

**Detection:** Check `hermes cron list` for `error: 402` on multiple jobs.

### 2. memories_local backfill separator

`backfill_memories_local.py` reads PG via `docker exec psql`. Field separator MUST be `\x01` (SOH), NOT `|`, because fact content contains pipes (URLs, markdown).

Use: `-tAF "\x01"` and `.split("\x01")` in Python.

### 3. Memory Gateway /recall/fast timeout

Default httpx timeout was 1.0s — too short for cold-start (Gemini embed ~150ms + rerank ~400ms + network jitter). First call after cache expiry → 502.

**Fix:** Set timeout to 3.0s in `memory_gateway.py`.

### 4. memories_local collection deleted = /recall/ultra broken

The `/recall/ultra` endpoint queries `memories_local` Qdrant collection (384d). If this collection is missing (accidentally deleted), the voice recall path returns 0 results silently (with fallback to /recall/fast).

Recreate: PUT collection with `vectors.dense.size=384, distance=Cosine`, then run backfill.

### 5. Retain API format

Correct format for Hindsight retain:
```json
{"items": [{"content": "text", "context": "source"}], "async": true}
```
Field is `items` (array), NOT direct `content`. Field inside item is `content`, NOT `text`.

### 6. Write path flow (no new facts immediately)

Retain → Document (PG) → Hindsight worker extracts → memory_facts (if worthy)
→ pg_qdrant_sync_worker (2 min) → Qdrant memories
→ memories-local-sync (5 min) → Qdrant memories_local

A short/simple retain may not produce a new fact — the extractor judges whether content is "fact-worthy". This is normal. Consolidation runs can also produce 0 new facts.

## Why Qdrant over pgvector

At current scale (7K facts), pgvector would work (~30-50ms). But:
1. Voice streaming (Gemini Live) needs <50ms including embed — pgvector at 100K+ hits 100-200ms
2. Planned data ingestion (mails, bio, finance, navigation) will push past 100K
3. Measured: Qdrant 4.7x faster than PG recall on this deployment

Keep both: PG = truth + graph. Qdrant = speed + semantic recall.

## Why Two Dimensions (768d + 384d)

| Collection | Model | Dim | Latency | Quality | Use |
|---|---|---|---|---|---|
| memories | Gemini Embed 2 (API) | 768d | ~150ms (API call) | ~95% | Standard recall |
| memories_local | all-MiniLM-L6-v2 (local CPU) | 384d | ~7ms (no network) | ~80% | Voice streaming |

Cannot mix: cosine similarity is meaningless across different embedding spaces. Separate collections, separate sync pipelines.

## Quick Diagnostics

**All crons failing?** → Check provider credits or routing. `hermes cron list` shows errors.

**No new facts in 7+ days?** → Check write-worker health + cron statuses + last `created_at` in memory_facts.

**Voice recall returning 0 results?** → Check memories_local collection exists and has points. Check local-embed service (8896) is running.

**Drift growing?** → Check timers are active: `systemctl list-timers | grep sync`

**Memory Gateway 502?** → Cold start timeout. Check hybrid-search is responsive directly, then increase timeout.

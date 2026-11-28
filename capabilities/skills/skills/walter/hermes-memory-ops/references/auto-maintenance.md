---
name: memory-auto-maintenance
description: W.Alter memory system auto-maintenance — health watchdogs, sync timers, importance decay, usage tracking, and cron job routing. All no-LLM scripts ($0/month).
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [memory, maintenance, watchdog, decay, sync, cron]
---

# Memory Auto-Maintenance

Use when diagnosing, repairing, or extending W.Alter's memory maintenance layer. Also use when cron jobs fail silently or memory ingestion stops.

## Architecture Overview

```
Health Watchdog (5min) → Telegram alert if any service down
PG→Qdrant 768d (2min timer) → pg-qdrant-sync.service
PG→Qdrant 384d (5min timer) → memories-local-sync.service
Kardex→Hindsight (5min timer) → kardex-hindsight-sync
Importance Decay (daily 2h) → boost used, decay forgotten, archive dead
Usage Tracking (real-time) → fire-and-forget in hybrid-search
```

All maintenance is script-based, $0/month, no LLM dependency.

## Health Watchdog

- Script: `~/.hermes/scripts/memory_health_check.sh`
- Frequency: every 5 minutes (cron no_agent)
- Deliver: telegram (only on failure — watchdog pattern)
- Checks 8 things: Hindsight API, Hybrid Search, Write Worker, Memory Gateway, Local Embed, Qdrant, PG, systemd services
- Drift monitoring: alerts if PG↔Qdrant(768d) drift > 100, or PG↔Qdrant(384d) drift > 200
- Auto-restart: attempts `systemctl restart` on failed services

## Sync Timers

### PG→Qdrant 768d (pg-qdrant-sync.timer, 2min)
- Processes `memory_outbox` entries (INSERT/UPDATE events)
- Embeds via Gemini Embedding 2 (outputDimensionality=768)
- Script: `/root/.hermes/services/jarvis/pg_qdrant_sync_worker.py --incremental`

### PG→Qdrant 384d (memories-local-sync.timer, 5min)
- Backfills new facts into `memories_local` collection using local MiniLM
- Script: `/root/.hermes/services/jarvis/backfill_memories_local.py`
- Uses SOH (\x01) as psql field separator to handle pipe characters in content

### Kardex→Hindsight (kardex-hindsight-sync.timer, 5min)
- Syncs journal entries, psychological claims, preferences from Kardex to Hindsight
- Script: `/root/.hermes/services/jarvis/kardex_hindsight_sync.py`
- Idempotent via `kardex.hindsight_sync_state` table (tracks last_synced_id per table)
- Formats: `[JOURNAL] content`, `[PSYCHE/dim] claim`, `[PREF/cat] pref (polarity)`

## Importance Decay

- Script: `~/.hermes/scripts/memory_importance_decay.py`
- Schedule: daily at 02:00 UTC (cron no_agent)
- Logic:
  1. Boost: facts used in last 7 days → importance += usage_count × 0.02 (cap 0.95)
  2. Decay: facts WITH `last_used_at NOT NULL` AND unused 30+ days → importance -= 0.03
  3. Archive: tracked + never used + >90 days + importance < 0.1 → status='archived'
- Safety guard: NEVER touches facts with `last_used_at = NULL` (no tracking history)
- MUST disable outbox trigger before mass updates (see pitfalls)

## Usage Tracking

- Location: `hybrid-search.py`, step 3.5 after rerank
- Function: `_track_usage(point_ids)` — fire-and-forget daemon thread
- Updates: `usage_count += 1, last_used_at = NOW()` on matched `memory_facts`
- Key: uses `pg_memory_id` from Qdrant payload, NOT the Qdrant point UUID (they differ!)
- Cap: 20 IDs per call max

## Cron Job Routing

All cron jobs that need an LLM agent MUST have explicit model/provider:
- Recommended: `gemini-3.5-flash` via `kie` provider
- If left as inherited (null), they may resolve to OpenRouter via fallback_providers
- OpenRouter credit exhaustion = silent nightly failures (discovered: 6 jobs dead 13 days)

Jobs that don't need reasoning → convert to `no_agent` scripts:
- Health Check ✓ (bash)
- AI Offers Collector ✓ (python)
- Memory Importance Decay ✓ (python)

## Critical Pitfalls

### Outbox flooding from mass UPDATE
The `memory_facts_outbox_aiu` trigger fires on ANY update to memory_facts.
A mass UPDATE (importance decay, reset) creates N outbox entries = N Gemini Embed calls.
Fix: disable trigger before, re-enable after:
```sql
ALTER TABLE memory_facts DISABLE TRIGGER memory_facts_outbox_aiu;
-- ... mass update ...
ALTER TABLE memory_facts ENABLE TRIGGER memory_facts_outbox_aiu;
```

### retain_every_n_turns: 9999 kills ingestion
File `~/.hermes/hindsight/config.json` controls the Hindsight plugin behavior.
If `retain_every_n_turns` is high (9999) or `auto_retain` is false, the plugin never retains.
Correct values: `retain_every_n_turns: 1`, `auto_retain: true`.
This is DIFFERENT from `config.yaml memory.flush_min_turns` (which is a Hermes-level nudge).

### Gemini Embedding 2 dimension mismatch
Model now defaults to 3072d. Qdrant collection is 768d.
Hindsight API has `HINDSIGHT_API_EMBEDDINGS_GEMINI_OUTPUT_DIMENSIONALITY` env var (default=768 in code).
Raw API calls must include `outputDimensionality: 768` explicitly.

### Backfill separator
`psql -tAF "|"` breaks on content containing pipe characters.
Use `psql -tAF "\x01"` (SOH char) and split on `"\x01"` in Python.

### memories_local collection
Must be 384d Cosine with named vector "dense".
Created separately from the main `memories` (768d).
Different embedding model = different vector space = MUST be separate collection.

## Verification Commands

Check sync health:
```bash
~/.hermes/scripts/memory_health_check.sh  # silent = healthy
```

Check sync status:
```bash
systemctl status pg-qdrant-sync.timer memories-local-sync.timer kardex-hindsight-sync.timer
```

Check usage tracking is working:
```sql
SELECT COUNT(*) FROM memory_facts WHERE usage_count > 0;
SELECT COUNT(*) FROM memory_facts WHERE last_used_at > NOW() - INTERVAL '1 hour';
```

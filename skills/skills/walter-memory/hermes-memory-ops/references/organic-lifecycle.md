---
name: memory-organic-lifecycle
description: "Organic memory lifecycle — usage tracking, importance decay, Kardex psyche sync, health watchdog, and cron routing patterns for W.Alter memory stack."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [memory, organic, decay, kardex, psyche, watchdog, usage-tracking]
    triggers:
      - memory decay
      - importance tracking
      - kardex sync
      - memory health
      - journal entries
      - psyche profile
      - cron provider routing
---

# Memory Organic Lifecycle

Patterns for making W.Alter's memory breathe — usage tracking, importance decay, Kardex psyche integration, and self-repair. Complements the jarvis-memory-system skill (architecture/ports/services).

## Usage Tracking

After each recall, hybrid-search.py increments usage stats on returned facts.

Implementation in `hybrid-search.py`:
- `_track_usage(point_ids)` — fire-and-forget via background thread
- Uses `pg_memory_id` from Qdrant payload (NOT Qdrant point UUID — they differ)
- Updates `memory_facts SET usage_count = usage_count + 1, last_used_at = NOW()`
- Capped at 20 facts per call, never blocks the recall response
- Requires `import subprocess, threading` in hybrid-search.py

Key: Qdrant payload contains `pg_memory_id` which maps to `memory_facts.id`. The Qdrant point UUID is a separate deterministic hash.

## Importance Decay

Script: `/root/.hermes/scripts/memory_importance_decay.py`
Cron: `Memory Importance Decay` — daily 2h UTC, no_agent, deliver=local

Rules:
1. Boost: facts used in last 7 days, importance += 0.02 per usage_count (cap 0.95)
2. Decay: facts with last_used_at NOT NULL AND unused 30+ days, importance -= 0.03
3. Archive: importance < 0.1 AND tracked AND usage_count=0 AND >90 days old

### Critical Guard

NEVER decay facts with `last_used_at IS NULL`. These have never been tracked — penalizing them mass-decays the entire corpus on first activation.

First run without this guard decayed 7637 facts and archived 1. The fix: only decay facts that have had a chance to be recalled (last_used_at IS NOT NULL).

## Kardex Psyche Layer

Lucas = contact_id 0 in `kardex.contacts` (relationship_type = 'self').

### Tables used

- `kardex.psychological_claims` — dimensions: cognitive_style, control_need, perfectionism, autonomy, cost_consciousness, directness, builder_identity
- `kardex.preferences` — categories: communication, tech, lifestyle, work. Polarity: positive/negative
- `kardex.journal_entries` — free text entries with mood, energy_level, emotional_tags, entry_type, privacy_level

### Journal entry_types

thought, dream, reflection, rant, decision, memory, aspiration

### Kardex to Hindsight sync

Script: `/root/.hermes/services/jarvis/kardex_hindsight_sync.py`
Timer: `kardex-hindsight-sync.timer` (every 5 min)

Format retained:
- Journal: `[JOURNAL] content`
- Claims: `[PSYCHE/dimension] claim`
- Preferences: `[PREF/category] preference (polarity)`

State tracking: `kardex.hindsight_sync_state` table (last_synced_id per table).

### Why not PG triggers?

Attempted and failed:
- `memory_outbox.memory_fact_id` has FK to `memory_facts` — random UUIDs rejected
- `memory_outbox.event_type` has CHECK constraint (allowed values hardcoded)
- Triggers with CASE on NEW.field fail across tables with different schemas
- Decoupled script calling retain API directly is simpler and maintainable

## Memory Health Watchdog

Script: `/root/.hermes/scripts/memory_health_check.sh`
Cron: every 5 min, no_agent, deliver to Telegram. Silent when healthy.

Checks (9 total):
1. Hindsight API (:8888)
2. Hybrid Search (:8889)
3. Write Worker (:8890)
4. Memory Gateway (:8891)
5. Local Embedding (:8896)
6. Qdrant
7. PostgreSQL
8. Systemd services (auto-restart attempted)
9. PG-Qdrant drift: 768d threshold >100, 384d threshold >200

Cost: zero (bash script, localhost curls, no LLM).

## Cron Provider Routing Rule

Always set explicit model+provider on LLM cron jobs. Never rely on inherited resolution.

Failure mode: default provider resolved to OpenRouter via `fallback_providers`. OpenRouter had no credits. All 6 cron jobs failed silently for 13 days. Memory ingestion stopped.

Fix: pin each job to `kie / gemini-3.5-flash` explicitly.

When to use which model for crons:
- gemini-3.1-flash-lite: structured extraction only (write worker, no tool-calling)
- gemini-3.5-flash: agent crons with tool-calling (dreaming, connectors, analysis)
- no_agent scripts: deterministic tasks (health check, sync, decay, collection)

Cost: Flash Lite vs Flash 3.5 difference is ~$0.40/month total. Not worth optimizing.

## memories_local Backfill

Script: `/root/.hermes/services/jarvis/backfill_memories_local.py`
Timer: `memories-local-sync.timer` (every 5 min)

### Pitfall: field separator

PG query MUST use `\x01` (SOH character) as field separator, NOT `|`. Fact content frequently contains pipe characters, causing `ValueError: too many values to unpack`.

```python
# WRONG
["docker", "exec", "hindsight-pg", "psql", ..., "-tAF", "|", "-c", sql]
# RIGHT
["docker", "exec", "hindsight-pg", "psql", ..., "-tAF", "\x01", "-c", sql]
```

### Performance

7637 facts backfilled in ~9 minutes (batch_size=100, ~70ms per individual embedding on CPU).

## Sync Timers

| Timer | Freq | Purpose |
|---|---|---|
| pg-qdrant-sync | 2 min | PG → Qdrant 768d (Gemini embed, already in PG) |
| memories-local-sync | 5 min | PG → Qdrant 384d (re-embeds via local MiniLM) |
| kardex-hindsight-sync | 5 min | Kardex claims/prefs/journal → Hindsight retain |

## Models per Layer

| Layer | Model | Cost |
|---|---|---|
| Extraction | Gemini 3.1 Flash Lite | Free |
| Primary embedding (768d) | Gemini Embedding 2 | Free |
| Local embedding (384d) | all-MiniLM-L6-v2 | CPU |
| Reranker | FlashRank / ZeRank-2 | CPU/API |
| Cron agents | gemini-3.5-flash (Kie) | ~$0.004/run |
| Maintenance scripts | No LLM | $0.00 |

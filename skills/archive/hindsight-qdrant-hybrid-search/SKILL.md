---
name: hindsight-qdrant-hybrid-search
description: "Deploy and maintain Hindsight hybrid memory: Qdrant (local vector DB), Gemini Embed 2 (API), ZeRank-2 reranking (API), async write path worker. Replaces PG+pgvector for 40x faster search."
triggers:
  - Qdrant deployment or migration
  - Hindsight memory performance issues
  - Hybrid search setup
  - Hybrid Search read-path changes or API compatibility checks
  - Memory context injection compiler / "Memory Sniper" tuning
  - Write path / async extraction
  - Reranker swap (FlashRank ↔ ZeRank-2 ↔ Cohere)
---

# Hindsight Qdrant Hybrid Search

## Always-on rules

- Read path MUST be synchronous/blocking — the LLM needs memory BEFORE responding, not after.
- Write path MUST be async — extraction runs in background, never blocks conversation.
- Redact secrets before displaying config/env/logs. Never print API keys, tokens, full connection strings, or auth headers.
- Preserve existing `/recall` request fields and `results[]`, `timings`, `query` response fields.
- Redact secrets before adding any memory text to `memory_context` or logs. Keep logs to counts/keys/timings, not full memory contents.
- The read path MUST include `must_not=[FieldCondition(key="invalidated", match=MatchValue(value=True))]` in the Qdrant query filter.
- Do not let the Hindsight plugin retain every conversation turn directly into the Hindsight API while the PG-first `write-worker` also exists.
- External chat connectors must not bulk-retain personal chat logs into Hindsight by default.
- Consolidated facts MUST be written to PostgreSQL first via the memory truth-store path, then synced to Qdrant through `memory_outbox` / `pg_qdrant_sync_worker.py`.
- Same check applies to `write-worker.service` and `hybrid-search.service` — always verify the running process env, not just the .env files.
- Inspect PG via schema introspection first. Do not assume columns like `source` exist.
- Duplicate counts are not automatically delete-worthy. Report exact and near duplicates, but prefer dream-cycle/consolidation merge/invalidation over destructive manual deletes.

## Read/Write Path Separation

- **Read path MUST be synchronous/blocking** — the LLM needs memory BEFORE responding, not after
- **Write path MUST be async** — extraction runs in background, never blocks conversation
- Trigger write every ~10 exchanges or on context compression
- The write worker HTTP API: `POST /process` with `{"turns": [...], "bank_id": "walter"}`

## References (read with skill_read(name, file_path=...))

- `references/audit-and-autopilot.md` — Read when auditing the complete memory stack or configuring, validating, and troubleshooting automated maintenance.
- `references/deployment-and-integration.md` — Read when deploying or migrating the stack, configuring providers, changing extraction hooks, implementing Memory Sniper, or integrating the user profile compiler.
- `references/dual-path-recall-architecture.md` — Read when debugging recall routing, scores, coverage, PG-to-Qdrant synchronization, or noisy context injection.
- `references/extraction-quality-testing.md` — Read when validating extraction quality, cost, and recall after changing extraction models.
- `references/memory-connectors.md` — Read when configuring or troubleshooting Telegram/Beeper ingestion, retain payloads, cron credentials, or personal chat ingestion guards.
- `references/model-selection-for-extraction-consolidation.md` — Read when selecting or swapping compression, extraction, or consolidation models and checking benchmark-backed recommendations.
- `references/performance-and-scaling.md` — Read when comparing measured recall latency, interpreting historical benchmarks, or planning capacity and reranker limits.
- `references/pg-qdrant-lifecycle-hardening-2026-05-22.md` — Read when changing fact lifecycle, outbox synchronization, TTL expiry, dream-cycle consolidation, deterministic IDs, or orphan cleanup.
- `references/troubleshooting.md` — Read when diagnosing vector formats, embedding dimensions, reranker calls, systemd environment overrides, or provider configuration failures.
- `references/user-profile-memory-stratification.md` — Read when deciding which user information belongs in the canonical profile, episodic evidence, Kardex, or sensitive contextual signals.
- `references/voice-fastpath-and-noisy-ingestion-2026-05-22.md` — Read when debugging the Gemini Live voice recall fast path, bank labels, or quarantining noisy Beeper/WhatsApp ingestion.

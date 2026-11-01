---
name: hindsight-memory-consistency
category: devops
description: Audit and repair Hindsight PG↔Qdrant memory consistency, especially distinguishing raw memory_units history from active memory_facts search index.
tags: [hindsight, memory, qdrant, postgres, consistency, drift]
created: 2026-06-29
---

# Hindsight Memory Consistency

Use this when Monsieur asks whether Hindsight memory is clean, whether there is PG↔Qdrant drift, or whether the recall index matches the source of truth.

## Core model

PostgreSQL is the source of truth, but not every PG table should match Qdrant one-for-one.

- `memory_units`: raw/historical unit store. It can be much larger than Qdrant.
- `memory_facts`: canonical lifecycle-managed facts. This is the table Qdrant indexes.
- Qdrant `memories` points carry payload key `pg_memory_id`, which refers to `memory_facts.id`.
- The Qdrant point ID itself is a deterministic derived UUID, so do not compare Qdrant point IDs directly to PG UUIDs.

## Clean-state invariant

A clean Hindsight search index means:

1. Every active, canonical, non-critical, non-expired `memory_facts` row is present in Qdrant with payload `pg_memory_id = memory_facts.id`.
2. No inactive fact (`superseded`, `invalidated`, `expired`, `historical`, archived) remains present in Qdrant.
3. `memory_outbox` has 0 pending rows.
4. PG sync status has no active `qdrant_sync_status='error'` rows.
5. Sync worker health reports 100% coverage and 0 sync errors.

Do not call it drift just because `memory_units` is larger than Qdrant. That is usually expected. The useful drift check is active `memory_facts` vs Qdrant payload `pg_memory_id`.

## Verification workflow

1. Check the sync worker health first.
2. Scroll Qdrant `memories` with payloads and collect every payload `pg_memory_id`.
3. Query `memory_facts` from PG.
4. Count:
   - active facts missing from Qdrant;
   - inactive facts still present in Qdrant;
   - sync-status states by `(status, qdrant_sync_status, present_in_qdrant)`.
5. Separately check `memory_outbox` pending count, `memory_units.embedding IS NULL`, and exact duplicate excess in `memory_units`.

## Repair workflow

For active facts stuck in error/unsynced state, run the PG→Qdrant sync worker in full-run mode with a safe limit, then re-check health.

For inactive facts still present in Qdrant, delete the point using the deterministic point ID derived from the PG fact UUID (`uuid.UUID(md5(fact_id).hexdigest())`) and set that fact's `qdrant_sync_status='deleted'` in PG.

Always verify after repair: active missing must be 0, inactive present must be 0, outbox pending must be 0, and sync errors must be 0. The job is not finished until those numbers are checked. Naturally, the database will not congratulate you for almost-clean.

## Pitfalls

- Comparing `memory_units` to Qdrant creates a false drift alarm; use `memory_facts`.
- Comparing Qdrant point IDs to PG IDs also creates a false drift alarm; compare Qdrant payload `pg_memory_id` to `memory_facts.id`.
- Multiline SQL passed via shell `-c` can be fragile through wrappers; use a heredoc or a script when the query is non-trivial.
- `memory_links` can be huge without proving recall-index drift. Treat link density as a graph/storage issue, not a PG↔Qdrant consistency issue.

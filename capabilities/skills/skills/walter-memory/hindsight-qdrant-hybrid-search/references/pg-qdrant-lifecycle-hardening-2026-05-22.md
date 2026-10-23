# PG→Qdrant lifecycle hardening — 2026-05-22

## Problem
The memory stack had the right components, but Qdrant was not a pure derived index. `write_worker.py` and `dream_cycle.py` could create direct Qdrant points, some with UUID4 IDs and no `pg_memory_id`. That made supersession, expiry, and reconciliation unreliable.

## Durable pattern
- PostgreSQL `memory_facts` is the source of truth.
- Qdrant `memories` is an active semantic index only.
- Every durable fact needs a stable `fact_key` and `value_hash`.
- Same `fact_key` + same `value_hash` = refresh existing active fact.
- Same `fact_key` + different `value_hash` = close old fact (`superseded`, `canonical=false`, `valid_until=now`) and insert new active canonical fact.
- `expires_at` handles TTL-based auto-expiry for non-permanent facts.
- `memory_outbox` drives all Qdrant changes.
- Qdrant point IDs should be deterministic UUIDs derived from PG fact IDs.

## Migration applied
Columns added to `memory_facts`:
- `fact_key`
- `value_hash`
- `expires_at`
- `last_seen_at`

Trigger/function added:
- `memory_facts_outbox_aiu`
- `expire_stale_memory_facts()`

Constraint update:
- `qdrant_sync_status` allows `deleted` for facts removed from Qdrant.

## Workers
`write_worker.py` should write to PG first and optionally run incremental sync; it must not upsert Qdrant directly.

`pg_qdrant_sync_worker.py` should:
- process `memory_outbox`
- upsert only `active + canonical + non-expired + non-critical` facts
- delete Qdrant points for superseded/expired/archived facts
- mark deleted rows with `qdrant_sync_status='deleted'`

`dream_cycle.py` must consolidate via PG, not direct `qdrant.upsert(source='dream_dedup')`.

## Verification pattern
1. Insert fact A with a stable `fact_key`.
2. Sync incremental.
3. Insert fact B with same `fact_key` and different `value_hash`.
4. Sync incremental.
5. Expect exactly one active canonical fact; old fact is superseded and deleted from Qdrant.

Expected shape:
```text
old: status=superseded, canonical=false, qdrant_sync_status=deleted, superseded_by=<new_id>
new: status=active, canonical=true, qdrant_sync_status=synced, supersedes=<old_id>
outbox pending: 0
```

## Orphan cleanup
Qdrant points with no `pg_memory_id` are legacy orphans. Backup them to JSON before deletion, then remove them from the active index. After cleanup, active PG facts and Qdrant point count should match under active-index policy.

## Performance note
Measured on this deployment at ~7.7k active memories:
- PG exact/current queries: sub-ms to ~2ms.
- Qdrant raw warm vector search: p50 ~34ms.
- Hybrid Search `:8889`: ~479ms end-to-end.
- Hindsight PG recall `:8888`: ~2265ms end-to-end.

PG is for exact truth/audit; Qdrant is for fuzzy semantic recall and context injection.
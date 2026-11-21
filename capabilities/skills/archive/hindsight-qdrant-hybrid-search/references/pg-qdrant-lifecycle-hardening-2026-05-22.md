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

## Dream Cycle (Nocturnal Consolidation)

Script: `/root/.hermes/services/dream_cycle.py`
Wrapper: `/root/.hermes/scripts/run_dream_cycle.sh` (loads env vars)
Timer: `dream-cycle.timer` → 4h05 UTC daily (±5min random delay)
Logs: `/root/.hermes/logs/dream_status.log` + `dream_last_run.json`

### Three Tasks

1. **Hard Delete** — Scans Qdrant for `invalidated=True` facts, permanently deletes them. Reduces collection bloat from write-path invalidation.

2. **Deduplication** — Loads active Qdrant facts with vectors, computes pairwise cosine similarity. Groups with sim > 0.95 are sent to the consolidation LLM for merge decision. Consolidated facts MUST be written to PostgreSQL first via the memory truth-store path, then synced to Qdrant through `memory_outbox` / `pg_qdrant_sync_worker.py`. Never create direct `dream_dedup` Qdrant-only points; they become orphans without `pg_memory_id` and break PG→Qdrant reconciliation. Old duplicate PG facts should be marked `superseded/canonical=false/valid_until=now/qdrant_sync_status=pending`, then the sync worker deletes their Qdrant points.

3. **Health Check** — Runs 3 recall queries against known entities (Scena, Lucas, Hindsight). Logs PASS/FAIL with ZeRank-2 scores to `dream_status.log`.

### Dream Cycle Pitfalls

- **Script corruption from secret redaction**: If `dream_cycle.py` shows `SyntaxError: unterminated string literal` at API key lines, the file was corrupted by a redaction tool replacing `os.getenv("KEY", "")` with `os.get...EY", "")`. Fix: replace with proper `os.getenv()` calls. See `references/memory-connectors.md` for detection/fix commands.
- **Model name must include `-preview` suffix**: Default `gemini-3.1-flash-lite` → 403 Forbidden. Correct: `gemini-3.1-flash-lite-preview`.
- **Cosine threshold 0.92 is too aggressive** — produces 50+ groups on 280 facts. Use 0.95 (produces ~15 groups).
- **Limit to 15 groups per run** — each group takes ~15s (extraction LLM + Gemini + Qdrant). 50 groups = 12min, too long for cron.
- **Dream-cycle must not write Qdrant directly** — route consolidated facts through PostgreSQL truth-store first (`upsert_facts_to_pg` or equivalent), then let `memory_outbox`/`pg_qdrant_sync_worker.py` update Qdrant. Direct `qdrant.upsert(source="dream_dedup")` creates orphan points without `pg_memory_id`; back them up and delete from the active index if found.
- **Qdrant payload bank label matters** — `hybrid_search.py` filters on `bank_id="walter"`. PG `memory_facts.scope` may be `global`; do not copy `scope` into `bank_id`. `pg_qdrant_sync_worker.py` must set payload `bank_id` from `BANK_ID` env/default `walter`, while keeping `scope` separately. Symptom: Qdrant `/health` shows thousands of points but `/recall` returns `candidates_count=0` / `reason=no_documents`.
- **Gemini embed dimension mismatch** — `gemini-embedding-2-preview` returns 3072 dims by default. Must include `"output_dimensionality": 768` in the request body.
- **qdrant variable scope in async** — pass `qdrant: QdrantClient` as parameter to `merge_duplicates()`, don't call `get_qdrant()` inside the async function.
- **Health checks must use REAL facts** — test data (Yamaha, Nextcloud port, etc.) gets deleted. Use stable facts like Scena Factory, Lucas, Hindsight.
- **Model selection matters** — see `references/model-selection-for-extraction-consolidation.md` for benchmark-backed picks. The consolidation LLM (dedup merge decisions) needs good reasoning; `gemini-3.1-pro-preview` (intel=57, free tier via AI Studio) is recommended over low-intelligence models.

### Systemd Timer

```bash
# /etc/systemd/system/dream-cycle.service
[Unit]
Description=Hindsight Dream Cycle - Consolidation
After=network.target qdrant.service hybrid-search.service write-worker.service

[Service]
Type=oneshot
ExecStart=/root/.hermes/scripts/run_dream_cycle.sh

# /etc/systemd/system/dream-cycle.timer
[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true
RandomizedDelaySec=300
```

### Test Data Cleanup

After running integration tests, clean test facts from Qdrant:
```python
# Match by source="write_worker" + test patterns (Yamaha, Nextcloud 8080, Plex port, NAS Synology, Oracle IP)
# Also check source="dream_dedup" for contaminated consolidated facts
# Use regex patterns, not exact match
```

See `references/pg-qdrant-lifecycle-hardening-2026-05-22.md` for the production hardening pattern: PG truth store, `fact_key`/`value_hash`, TTL expiry, outbox sync, deterministic Qdrant IDs, dream-cycle consolidation through PG, orphan cleanup, and measured PG vs Qdrant latencies.

See **`references/dual-path-recall-architecture.md`** for the full PG vs Qdrant recall path breakdown, including which endpoints return what scores and coverage.

See **`references/voice-fastpath-and-noisy-ingestion-2026-05-22.md`** for the validated Gemini Live → voice_router → Qdrant fast-path, the `bank_id=walter` payload pitfall, and the Beeper/WhatsApp noisy ingestion quarantine pattern.

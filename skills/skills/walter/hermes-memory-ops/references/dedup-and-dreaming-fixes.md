# Dedup & Dreaming Fixes — June 2026

## Exact Dedup Script: ROLLBACK Fix

### Problem
`hindsight_pg_exact_dedup.py` wrapped everything in a single `BEGIN...COMMIT` CTE transaction. The `UPDATE memory_links SET from_unit_id = canonical_id` step violated the unique index `idx_memory_links_unique` on `(from_unit_id, to_unit_id, link_type, COALESCE(entity_id, '0000...'))` when:
- Canonical already had a link to the same target
- Multiple dupes pointed to the same target

Result: entire transaction ROLLBACK, script reported `ok=True` but `stdout` contained `BEGIN ROLLBACK` and no rows were deleted.

### Fix (verified working — 655 → 0 groups)
Replace UPDATE approach with 3-step CTE pattern:

```sql
-- Step 1: Copy unique links from dupes to canonical
INSERT INTO memory_links (...)
SELECT DISTINCT ON (...) ... FROM dupes d JOIN memory_links ml ON ml.from_unit_id = d.id
WHERE ml.to_unit_id NOT IN (SELECT id FROM dupes)  -- skip orphaned targets
ON CONFLICT DO NOTHING;

-- Step 2: Delete all links from/to dupes
DELETE FROM memory_links WHERE from_unit_id IN (SELECT id FROM dupes);
DELETE FROM memory_links WHERE to_unit_id IN (SELECT id FROM dupes);

-- Step 3: Delete dupes
DELETE FROM memory_units WHERE id IN (SELECT id FROM dupes);
```

**Why it works:** `ON CONFLICT DO NOTHING` silently skips conflicting links instead of rolling back the entire transaction. PostgreSQL CTEs see each other's changes within the same transaction.

### Key pitfalls discovered
1. `to_unit_id` FK constraint requires target to exist — filter with `WHERE ml.to_unit_id NOT IN (SELECT id FROM dupes)`
2. Script reports `ok=True` even on ROLLBACK — check `stdout` for `BEGIN ROLLBACK` vs `BEGIN COMMIT`
3. With 655 groups, need multiple runs at `--limit-groups 200 --max-delete 1000` (each run reduces count, new conflicts may emerge)

### Recommended batch parameters
```bash
# Fast cleanup backlog
python3 /root/.hermes/scripts/hindsight_pg_exact_dedup.py --apply --limit-groups 200 --max-delete 1000

# Steady-state maintenance (in systemd service)
--limit-groups 100 --max-delete 500
```

---

## Dreaming Script Fixes

### API Response Keys
The Hindsight API returns different keys than the script expected:
- Entities: `{"items": [...]}` NOT `{"entities": [...]}`
- Reflect: `{"text": "..."}` NOT `{"answers": [...]}`

### Consolidation is Async
`POST /consolidate` returns `{"operation_id": "..."}` immediately. Must poll `GET /operations/{id}` until `status=completed` (max 10 min, 5s intervals). The script was treating it as synchronous.

### Pipeline Order
1. **Exact dedup FIRST** (cheap, no LLM) — cleans text-identical duplicates
2. **Consolidation** (expensive LLM) — merges semantic near-duplicates on clean data

Running consolidation before dedup wastes LLM tokens processing obvious duplicates.

---

## Plugin Anti-Duplicate Hash Cache

Added `_retain_hash_cache` dict in the plugin's `_do_retain()` method. Stores `MD5(text) → timestamp` for 10 minutes. Before inserting, checks if identical text was recently retained and skips.

- Catches exact duplicates at ingestion time
- In-memory only (lost on gateway restart)
- TTL 10 minutes
- Location: `plugins/memory/hindsight/__init__.py` → `_do_retain()`

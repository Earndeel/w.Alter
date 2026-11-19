---
name: walter-memory-extraction-audit
description: Use when auditing Walter Memory extraction quality, backlog, temporal continuity, or readiness to resume extraction without starting a backfill.
---

# Audit Walter Memory extraction without changing state

## Establish scope and safety

1. Separate service health, extraction throughput, knowledge quality, and downstream continuity. An active service does not prove that knowledge is current.
2. Record the audit window and generation explicitly. The observed legacy producer was `l3.extract`, generation `g1`; verify these before reusing them as filters.
3. Use the existing authorized database connection through Walter's Python runtime (`walter-python`, with psycopg available). Do not invent a PostgreSQL address or bypass credential handling. If connection discovery is needed, load `vault-lookup`.
4. Run database inspection in a read-only transaction: `BEGIN READ ONLY;` and finish with `ROLLBACK;`. Do not run extraction, reconciliation, backfill, forced thread processing, or service restarts during the audit.

## Locate the implementation and declared signals

```sh
walter-memory health
walter-memory --help
sed -n '85,115p' /walter/cognition/memory/walter_memory/cli.py
grep -n '^def ' /walter/cognition/memory/walter_memory/extract2.py
grep -n 'extract2\.' /walter/cognition/memory/walter_memory/cli.py
```

Read relevant functions in `extract2.py` before interpreting counters or proposing a restart. The CLI exposes mutating operations: help and source inspection are not authorization to execute them.

Inspect Decision declarations at:

- `/walter/cognition/memory/manifest/decisions.json`
- `/walter/cognition/context/manifest/decisions.json`

Inspect `/walter/cognition/memory/walter_memory/runs.py` and `disclosure.py` for the actual run/thread/work contract. A declared signal is not evidence that live runs populate it.

## Inspect schema before writing aggregates

```sql
SELECT table_schema, table_name, column_name, data_type, udt_name
FROM information_schema.columns
WHERE (table_schema, table_name) IN (
  ('extraction','segments'), ('extraction','covered'),
  ('extraction','threads'), ('extraction','state'),
  ('core','events'), ('core','derived_items'),
  ('core','relationships'), ('runs','runs'), ('views','view')
)
ORDER BY table_schema, table_name, ordinal_position;
```

Hard-won pitfalls:

- `extraction.segments.items`, `reused`, and `superseded` were integer counters; `rejected` was a JSONB array. Neither `sum(rejected)` nor `jsonb_array_length(superseded)` is valid.
- `core.relationships` uses `predicate`, not `relation_type`.
- Do not repeatedly guess types after an SQL error. Reinspect schema, roll back the failed transaction, and open a fresh read-only transaction.

## Measure throughput and knowledge lifecycle

After confirming types, run an aggregate for the chosen window. Replace the example date deliberately:

```sql
SELECT source, status, count(*) AS segments,
       sum(items) AS items,
       sum(reused) AS reused,
       sum(superseded) AS superseded,
       sum(jsonb_array_length(coalesce(rejected, '[]'::jsonb))) AS rejected,
       round(sum(coalesce(cost_usd, 0))::numeric, 2) AS usd
FROM extraction.segments
WHERE created_at >= DATE '2026-11-03'
GROUP BY source, status
ORDER BY source, status;

SELECT kind, status, count(*) AS n,
       count(*) FILTER (WHERE valid_to IS NOT NULL) AS temporally_closed
FROM core.derived_items
WHERE generation = 'g1' AND derived_by = 'l3.extract'
GROUP BY kind, status
ORDER BY kind, status;

SELECT predicate, derived_by, generation, count(*) AS n,
       count(*) FILTER (WHERE valid_to IS NOT NULL) AS closed,
       max(created_at) AS latest_creation
FROM core.relationships
GROUP BY predicate, derived_by, generation
ORDER BY n DESC;
```

Check completed/expired attributes rather than assuming status alone expresses their lifecycle:

```sql
SELECT k, count(*)
FROM core.derived_items
CROSS JOIN LATERAL jsonb_object_keys(attributes) AS k
WHERE generation = 'g1' AND derived_by = 'l3.extract'
GROUP BY k ORDER BY count(*) DESC;
```

A relation that has never been closed is a temporal-quality warning, not proof that every instance is stale.

## Check duplication, backlog, and continuity separately

Measure normalized exact duplicates without displaying personal content:

```sql
WITH x AS (
  SELECT kind, lower(regexp_replace(content, '\W+', ' ', 'g')) AS normalized
  FROM core.derived_items
  WHERE generation = 'g1' AND derived_by = 'l3.extract'
    AND status = 'derived'
)
SELECT kind, count(*) AS live,
       count(*) - count(DISTINCT normalized) AS exact_duplicates
FROM x GROUP BY kind ORDER BY live DESC;
```

This is an exact-normalization check, not semantic deduplication. Do not launch an unbounded embedding self-join as a routine follow-up.

To assess backlog, compare source event dates with segment completion and coverage using the inspected schemas and implementation. Count eligible messages and volume by source; distinguish private/local-only inputs. Do not equate all events since the latest segment with eligible unprocessed work.

For Context continuity, inspect files under `/user/Lucas/state/context/shadow/preflight-*.jsonl`. Aggregate `runtime`, `mode`, and `plan.thread` assignments over the audit window rather than dumping full records. Compare those assignments with `runs.runs.thread_id`, run origins, and requested work routing after verifying their types and semantics. Shadow plans show proposed routing, not proof of successful extraction or recall.

## Check routing and report without resuming

```sh
walter-router route memory_extraction
walter-llm test-budget
walter-router plans consumption
```

`walter-router plans` alone requires a subcommand; use `consumption` for consumption inspection. Routing or budget availability does not authorize a paid extraction run.

Report separately:

- observation window, generation, and producer;
- completed/failed segments, produced/reused/superseded/rejected counts, and recorded cost;
- lifecycle coverage, duplication, and relation closure;
- eligible backlog versus raw event volume;
- continuity evidence and remaining unknowns;
- prerequisites for any proposed resumption.

State explicitly whether extraction remained untouched. Obtain approval before any write, restart, backfill, or reactivation.

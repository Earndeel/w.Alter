---
name: walter-memory-recall-regression
description: Use when Walter Memory recall or injected context loses answer quality after a provider migration, indexing change, or read-policy change.
---

# Diagnose and validate recall regressions

## Establish the baseline
1. Read the memory architecture and dated decisions before changing eligibility or provenance rules. Resolve the module with `walter path memory`; run Python with `walter-python`.
2. Inspect `walter_memory/agent_memory.py`, `search.py`, `read_policy.py`, `context.py`, and `gateway.py`. Trace the actual consumers: gateway recall, gateway context, runtime hook, and Hermes provider. A search-only test does not establish injected-context quality.
3. Locate a curated benchmark with queries, expected answers, and reference facts. Preserve its inputs and record the current commit. Back up affected files and data before mutation.
4. From the memory module directory, run both paths against the same benchmark:

```bash
walter-python bench/recall_bench.py --bench-dir "$BENCH_DIR" --path recall --show 3 --out "$REPORT_DIR/before_recall.json"
walter-python bench/recall_bench.py --bench-dir "$BENCH_DIR" --path context --show 3 --out "$REPORT_DIR/before_context.json"
```

Confirm script options against the current checkout before running. Keep benchmark data and outputs out of committed procedure text.

## Find the failing boundary
- Inspect `core.derived_items` status, `derived_by`, privacy class, source references, and source-event links. Compare stored facts with read-policy eligibility. Imported legacy facts can exist in the database yet be excluded from recall.
- Inspect `search.chunks` counts by kind, hidden state, and duplicate state. Check whether tool-call noise or quarantined material dominates candidates.
- Inspect the live schema before writing SQL. Do not assume a provenance column exists; this session found source references and event arrays instead.
- If host `psql` is unavailable, use the existing container client without printing credentials:

```bash
docker exec -i hindsight-pg psql -U hindsight -d hindsight -X -c '\d core.derived_items'
docker exec -i hindsight-pg psql -U hindsight -d hindsight -X -c '\d search.chunks'
```

- For provenance lookups into partitioned `core.events`, inspect `core.event_keys` and use event timestamps with IDs to permit partition pruning. Verify the query plan.
- Preserve canonical provenance and privacy checks when admitting legacy facts. Apply migrations through the supported memory library or gateway.

## Validate ranking, privacy, and cost
1. Compare knowledge facts and Kardex results with raw conversation fragments; inspect duplicate results and excluded noise.
2. Treat strict reference-word overlap and semantic answer availability as separate metrics. Manually inspect misses. Report each path separately and retain unmet acceptance targets.
3. If using `bench/recall_judge.py`, inspect its provider and cost behavior first. Run paid judging and reranking only within a bounded budget. Repeated benchmark variants multiply rerank calls.
4. Read `system.model_calls` schema, then aggregate recent calls by processor, provider, model, status, and cost. Use the Router-selected reranking role; do not hardcode a model.
5. Verify query and candidate privacy before external reranking. Test representative sensitive patterns: this session found that phone-number text could escape detection. Never equate a stored privacy label with proven detector coverage.

## Complete verification
Run relevant tests, `walter check`, and `walter-memory health`. After service changes, run `systemctl start memory-autopilot` and inspect the fresh report at `/root/.hermes/logs/memory-autopilot/latest.json`; inspect its actual fields before extracting a score. Check gateway and indexer journals for errors. Record the final metrics, remaining limitations, paid-call cost, and dated decision.

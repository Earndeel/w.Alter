---
name: walter-memory-retrieval-benchmark
description: Use when comparing Walter Memory embeddings or rerankers and diagnosing why retrieved sources disappear before reaching the agent's final context.
---

# Compare retrieval chains through final context

## Inspect the actual pipeline

Read `/root/.hermes/docs/walter-memory/ARCHITECTURE.md` and its adjacent `DECISIONS.md` before changing memory behavior. Inspect the current retrieval implementation, historically `/opt/walter-memory/walter_memory/search.py`; resolve the module's current location through `walter path memory` if it has moved.

Identify each candidate lane, deduplication step, reranking boundary, context budget and lane quota. Verify which lanes actually receive reranking. Do not assume original evidence and derived knowledge follow the same selection path.

## Freeze a comparable pilot

Create an isolated benchmark directory. Freeze the corpus and questions as JSON, recording SHA-256 hashes in a protocol file. Give every question expected source or chunk identifiers. Verify the hashes before each additional variant.

Use a reviewed corpus appropriate for the destination models. Apply existing privacy policies and obtain any required authorization before sending real memory content to cloud providers. Keep the active index and router selections unchanged.

Run these combinations against the same corpus and questions:

- Current embedding + current reranker.
- Candidate embedding + candidate reranker.
- Candidate embedding + current reranker, to isolate the embedding change.

Preserve the production retrieval path through final context selection. Record any substituted components or prepared caches, plus the actual reranking deadline. The observed pilot used a 3-second deadline; verify the current setting rather than assuming it.

## Trace where sources are lost

For every question and variant, retain expected identifiers and identifiers surviving each stage:

1. Candidate retrieval, separately for each lane.
2. Deduplication within each lane.
3. Reranking where applicable.
4. Lane allocation and final context selection.

Record final source hit, source rank, reciprocal rank, latency, API failures, timeout fallbacks, token usage and reported cost. Distinguish missing measurements from zero cost.

When a final source is missing, locate its first disappearance. A source retrieved successfully but discarded by a one-item evidence quota is a selection failure. Changing the reranker cannot recover that source if its lane never reaches the reranker.

## Validate changes and report limits

If modifying the shared memory facade, run the relevant existing tests, including these when present:

```sh
walter-python -m pytest -q /opt/walter-memory/tests/test_retrieval_calls.py /opt/walter-memory/tests/test_agent_memory.py /opt/walter-memory/tests/test_read_privacy.py
```

After changing memory services, run `systemctl start memory-autopilot` and inspect `/root/.hermes/logs/memory-autopilot/latest.json`.

Report candidate recall separately from final-context recall and ranking. State corpus size, question count, cache preparation, failures and timing limits. Precomputed document vectors can hide cloud embedding work that a live implementation would perform during deduplication.

Do not infer general model superiority from a small final-context difference. Explain the exact question and pipeline stage responsible before recommending a switch.

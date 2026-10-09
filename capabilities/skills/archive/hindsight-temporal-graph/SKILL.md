---
name: hindsight-temporal-graph
summary: Add Graphiti-like temporal graph, provenance, and lifecycle context to Hindsight using PostgreSQL as the truth store and Qdrant as a derived semantic index.
description: Use when planning, implementing, auditing, or troubleshooting a PG-first temporal graph/provenance sidecar for Hindsight memory. Covers additive schema design, write-path provenance, read-path graph context compilation, idempotent migration, validation, and rollback.
triggers:
  - Graphiti-like memory integration
  - Hindsight temporal graph
  - memory provenance
  - zombie facts / supersession / invalidation
  - PG-first memory graph
  - contextual recall with graph edges
---

# Hindsight Temporal Graph

## Purpose

Use this skill when Monsieur asks to improve Hindsight with Graphiti-like behavior without replacing the current architecture. The target architecture is:

- PostgreSQL remains the truth store.
- Qdrant remains the fast semantic index.
- A PostgreSQL sidecar adds temporal graph, provenance, and relation-aware context.
- Existing `/recall` compatibility is preserved; graph context is additive.

This is the pragmatic version of Graphiti: enough temporal graph to kill zombie facts, not a dependency cathedral. Civilization may yet survive.

## Design principles

1. **Additive sidecar first** — do not rewrite `memory_facts` or replace Qdrant.
2. **Idempotent migrations** — every schema change must be safe to re-run.
3. **PG-first lifecycle** — canonical/current state belongs in PostgreSQL; Qdrant is derived.
4. **No direct graph writes to Qdrant** — Qdrant stores semantic recall payloads, not source-of-truth graph state.
5. **Provenance by episode** — store compact redacted source batches, not raw unbounded transcripts.
6. **Read compatibility** — preserve `results[]`; add graph context under `memory_context`, `injection_context`, or equivalent additive fields.
7. **Sidecar failure must not block core memory writes** — graph/provenance operations should use savepoints or exception guards.

## Recommended schema

Add these sidecar tables:

- `hindsight_episodes`: redacted source batch with bank, source, content hash, compact content, metadata, timestamps.
- `hindsight_fact_provenance`: fact-to-episode/event evidence, evidence type, excerpt, metadata.
- `hindsight_fact_entities`: bridge from `memory_facts` to canonical `entities`.
- `hindsight_edges`: polymorphic graph edges between `fact`, `entity`, and `episode` nodes with `relation_type`, confidence, validity window, status, optional evidence fact and episode.
- `v_hindsight_active_edges`: view filtering active, non-expired graph edges.

Useful relation types:

- `mentions`: fact → entity.
- `supports`: episode → fact.
- `supersedes`: new fact → old fact.
- `superseded_by`: old fact → new fact.
- `contradicts`: fact → fact.

## Migration workflow

1. Inspect the existing PG schema before writing SQL. Confirm columns and constraints on `memory_facts`, `entities`, `memory_events`, and `memory_outbox`.
2. Create a database backup before applying schema changes.
3. Write one idempotent SQL migration for the sidecar.
4. Dry-run the migration transaction by replacing the final commit with rollback and applying it through PostgreSQL with stop-on-error enabled.
5. Apply the real migration only after the rollback dry-run passes.
6. Re-apply once to prove idempotency.
7. Backfill graph data by bank/scope. Many Hindsight installs use both `walter` and `global`; check before assuming one bank.

## PostgreSQL functions to include

A good implementation usually needs:

- `hindsight_normalize_entity_name(name)`
- `hindsight_upsert_entity(bank_id, name, metadata)`
- `hindsight_upsert_edge(...)`
- `hindsight_link_fact_entities(fact_id, bank_id, entities, source)`
- `hindsight_record_fact_provenance(fact_id, episode_id, memory_event_id, evidence_type, metadata)`
- `hindsight_link_fact_lifecycle(fact_id)`
- `hindsight_backfill_fact_graph(bank_id, limit)`

Install an `AFTER INSERT OR UPDATE` trigger on `memory_facts` for lifecycle-relevant columns such as tags, status, canonical, supersedes, superseded_by, contradicts, valid_until, scope, and project_id.

## Important implementation pitfall

PL/pgSQL variable names can collide with table column names inside `ON CONFLICT` clauses. For example, a local variable called `entity_id` can conflict with a table column called `entity_id`. Keep table columns clean and prefix variables, e.g. `v_entity_id`.

## Write-path integration

In the write worker:

1. Build a compact provenance episode from processed turns.
2. Redact likely secrets before storing the episode.
3. Pass `episode_id` into the fact upsert function.
4. Record provenance on insert, refresh, semantic merge, and supersession.
5. Merge new entity tags into existing facts on refresh/semantic merge.
6. Use savepoints for optional graph side effects so the core fact transaction can continue if the sidecar fails.
7. Leave Qdrant updates to the existing outbox/sync flow.

Redaction should catch token-like and credential-like strings, but do not log or display raw secrets while debugging.

## Read-path integration

In the recall service:

1. Keep `results[]` unchanged for client compatibility.
2. Add graph/provenance context only as additive compiled context.
3. Use a bounded recursive CTE over active graph edges.
4. Search both the requested bank and `global` if the deployment stores historical facts under `global`.
5. Match individual query tokens as well as the whole query string. Multi-word queries can otherwise miss relevant facts containing only one term.
6. Add timing/debug fields like `graph_ms`, `graph_count`, `graph_items`, and graph intent.
7. Truncate graph context under the same injection budget as the semantic memory context.

## Validation checklist

- Python files compile.
- SQL migration rollback dry-run passes.
- Real migration applies cleanly.
- Re-applying the migration is harmless.
- Backfill returns nonzero or explainable counts for facts/entities/lifecycle links.
- A throwaway-bank write test verifies:
  - value A inserted,
  - value B with same fact key supersedes A,
  - old fact is non-canonical and has `valid_until`,
  - new fact is active/canonical,
  - provenance rows exist,
  - edges exist for `mentions`, `supports`, `supersedes`, `superseded_by`,
  - all test rows are cleaned afterward.
- Restart affected read/write services.
- Health-check write and recall endpoints.
- Live recall proves graph context is active through timing/count fields and compiled context format.

## Rollback strategy

Because the graph is additive, prefer minimal rollback:

1. Disable graph-context read flags if present.
2. Restart the recall service.
3. Drop or disable the graph trigger if writes are affected.
4. Leave sidecar tables in place for inspection unless they are corrupt.
5. Restore the database backup only if core memory tables were damaged.

## Session reference

A concrete implementation note from the first production integration belongs in `references/temporal-graph-provenance-sidecar.md` when available. Keep references concise and task-focused, not a blow-by-blow diary.

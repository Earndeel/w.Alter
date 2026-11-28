-- Memory cleanup phase 1 (Monsieur's go of 2026-11-09; plan: docs/NETTOYAGE-2026-11.md § phase 1).
-- Drops the retired Hindsight cognitive layer and the mechanics of the pre-October pipeline, by an explicit list,
-- never `drop schema public` and never CASCADE. Schema `public` keeps the extensions Memory needs (vector, pg_trgm,
-- pgcrypto, unaccent: search.f_unaccent and every vector column depend on them).
--
-- Not dropped here, kept for review before any later deletion: the pre-October knowledge of `legacy`
-- (memory_facts, current_beliefs, preferences, decision_rules, project_states, hindsight_episodes, their provenance
-- and graph: hindsight_fact_provenance, memory_events, hindsight_edges, hindsight_fact_entities), user_model,
-- x_research. Hindsight's own memories already live in core.derived_items (derived_by = 'hindsight', g0, 34 493
-- rows: all of bank `walter`; bank `walter-shadow` was a mirror of Walter Memory, every document maps to a core row).
--
-- Rollback: the encrypted targeted dump next to the phase 1 restore point restores exactly these objects
-- (@instance/backups/changes/2026-11-09-memory-phase1/rollback/). Idempotent (IF EXISTS everywhere): a blank or test
-- database, which never had these objects, passes through unchanged.
begin;
set local lock_timeout = '5s';

-- 1. Kept legacy knowledge points at Hindsight entities (legacy.hindsight_fact_entities by foreign key,
--    legacy.hindsight_edges by id): copy the entities they cite into `legacy` and re-point the foreign key first,
--    so no provenance is broken when public.entities goes.
do $$
begin
  if to_regclass('public.entities') is not null and to_regclass('legacy.hindsight_fact_entities') is not null
     and to_regclass('legacy.hindsight_entities') is null then
    create table legacy.hindsight_entities as
      select e.* from public.entities e
      where e.id in (select entity_id from legacy.hindsight_fact_entities
                     union select to_node_id from legacy.hindsight_edges where to_node_type = 'entity'
                     union select from_node_id from legacy.hindsight_edges where from_node_type = 'entity');
    alter table legacy.hindsight_entities add primary key (id);
    comment on table legacy.hindsight_entities is
      'Copy (2026-11-09, cleanup phase 1) of the Hindsight entities cited by the kept legacy knowledge '
      '(hindsight_fact_entities, hindsight_edges), taken before public.entities was dropped.';
    alter table legacy.hindsight_fact_entities drop constraint hindsight_fact_entities_entity_id_fkey;
    alter table legacy.hindsight_fact_entities add constraint hindsight_fact_entities_entity_id_fkey
      foreign key (entity_id) references legacy.hindsight_entities (id) on delete cascade;
  end if;
end $$;

-- 2. Retired sync triggers on the kept legacy.memory_facts (they fed Qdrant and the Hindsight graph).
drop trigger if exists hindsight_memory_fact_graph_aiu on legacy.memory_facts;
drop trigger if exists memory_facts_outbox_aiu on legacy.memory_facts;

-- 3. Hindsight views and materialized view of `public`.
drop view if exists public.v_active_facts, public.v_pending_outbox, public.v_recent_audit,
                    public.v_hindsight_active_edges;
drop materialized view if exists public.memory_units_bm25;

-- 4. The 22 Hindsight tables of `public` (their sequences, indexes and constraints go with them).
drop table if exists
  public.memory_links, public.unit_entities, public.entity_cooccurrences, public.observation_history,
  public.invalidated_memory_units, public.memory_units, public.chunks, public.documents, public.entities,
  public.mental_model_history, public.knowledge_pages, public.mental_models, public.directives,
  public.async_operations, public.webhooks, public.llm_requests, public.graph_maintenance_queue,
  public.bank_stats_cache, public.audit_log, public.file_storage, public.alembic_version, public.banks;

-- 5. The 16 functions of the Hindsight era in `public` (none belongs to an extension).
drop function if exists
  public.schemas_with_pending_work(),
  public.memory_fact_qdrant_event_type(text, boolean, timestamp with time zone, timestamp with time zone),
  public.enqueue_memory_fact_sync(),
  public.expire_stale_memory_facts(),
  public.hindsight_normalize_entity_name(text),
  public.hindsight_upsert_entity(text, text, jsonb),
  public.hindsight_upsert_edge(text, text, uuid, text, uuid, text, real, timestamp with time zone,
                               timestamp with time zone, text, uuid, uuid, jsonb),
  public.hindsight_link_fact_entities(uuid, text, text[], text),
  public.hindsight_record_fact_provenance(uuid, uuid, uuid, text, jsonb),
  public.hindsight_link_fact_lifecycle(uuid),
  public.hindsight_memory_fact_graph_trigger(),
  public.hindsight_backfill_fact_graph(text, integer),
  public.banks_needing_consolidation(),
  public.schemas_with_expired_rows(text, text, integer),
  public.mental_models_with_cron(),
  public.schemas_with_expired_operations(integer);

-- 6. Pipeline mechanics of `legacy` (Qdrant outbox and sync state, empty audit/action tables) and the two router
--    schemas replaced by `models` on 2026-10-02 (public model catalogue, no personal data).
drop table if exists
  legacy.memory_outbox, legacy.units_sync_state, legacy.access_audit_log, legacy.action_requests,
  legacy.model_router__router_decisions, legacy.model_router__router_scores, legacy.model_router__internal_tests,
  legacy.model_router__pricing_snapshots, legacy.model_router__offers, legacy.model_router__community_evidence,
  legacy.model_router__benchmarks, legacy.model_router__endpoints, legacy.model_router__task_profiles,
  legacy.model_router__ingestion_runs, legacy.model_router__models,
  legacy.walter_router__router_scores, legacy.walter_router__change_log, legacy.walter_router__design_arena,
  legacy.walter_router__pricing, legacy.walter_router__benchmarks, legacy.walter_router__scrape_runs,
  legacy.walter_router__task_types, legacy.walter_router__providers, legacy.walter_router__models;

-- 7. Kardex → Hindsight sync cursor (the kardex-hindsight-sync timer was retired on 2026-10-19).
drop table if exists kardex.hindsight_sync_state;

-- 8. Voice index of Hindsight units, and Hindsight usefulness labels (already copied into the attributes of the
--    g0 items, key `usefulness`). The schemas go only if empty (RESTRICT).
drop table if exists walter_voice.unit_vectors;
drop schema if exists walter_voice;
drop table if exists walter_audit.memory_labels, walter_audit.memory_tags_before_quarantine;
drop schema if exists walter_audit;

commit;

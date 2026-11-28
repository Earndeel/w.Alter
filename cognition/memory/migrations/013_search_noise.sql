-- Recall repair (2026-10-19): why a chunk is out of recall, and vector indexes per search lane.
-- The index stays derived: core.events is untouched, `walter-memory index --hide-noise` recomputes hidden_reason.
alter table search.chunks add column if not exists hidden_reason text;
update search.chunks set hidden_reason = 'quarantined' where hidden and hidden_reason is null and kind = 'derived';
update search.chunks set hidden_reason = 'retracted' where hidden and hidden_reason is null and kind <> 'derived';

-- Run outside a transaction (CONCURRENTLY): exact scans cost 100-180 ms per lane on 280k chunks.
-- Lane predicates match search.search(): knowledge = kind 'derived', evidence = everything else.
set maintenance_work_mem = '1GB';
set max_parallel_maintenance_workers = 0;  -- parallel builds need more /dev/shm than the container has
create index concurrently if not exists chunks_vec_knowledge on search.chunks
  using hnsw (embedding vector_cosine_ops) where kind = 'derived' and not hidden and dup_of is null;
create index concurrently if not exists chunks_vec_evidence on search.chunks
  using hnsw (embedding vector_cosine_ops) where kind <> 'derived' and not hidden and dup_of is null;
-- Retractions are rare; readers look them up by target without scanning every partition's payload.
create index if not exists events_retracted_target on core.events ((payload->>'target_event_id'))
  where event_type = 'event.retracted';

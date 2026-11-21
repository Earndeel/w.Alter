-- 2026-11-19 (lot P1 des projections, latence): the projection reads the recent changes of a project (replaced
-- states, advanced goals, contradictions) and the derived links of its items. Two small partial indexes, read path
-- only. Built concurrently (migrations run in autocommit), idempotent.
create index concurrently if not exists derived_changes_recent on core.derived_changes (at)
    where reverted_at is null and not staged and op in ('supersede', 'advance', 'contest');
create index concurrently if not exists provenance_derived_source on core.provenance (source_id)
    where target_table = 'derived_items' and source_type = 'derived';

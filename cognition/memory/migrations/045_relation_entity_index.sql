-- 2026-11-19 (lot P3, docs/PROJECTIONS.md § 10): the relational projection reads the knowledge about one person by
-- core.derived_items.subject_entity_ids. Without an index that is a scan of every g1 item (24 ms of the 50 ms the
-- projection may take). An access path only, no new data. Additive, idempotent.
create index if not exists derived_g1_subject_entities on core.derived_items using gin (subject_entity_ids)
    where generation = 'g1';

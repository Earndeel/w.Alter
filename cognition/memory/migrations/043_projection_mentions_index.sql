-- 2026-11-19 (lot P1 des projections): a project's state also reads the status statements made about it under
-- another subject (« Hermes est arrêté » said about W.Alter): items whose attributes.projects names the project.
-- One partial GIN index for the `?|` lookup; read path only, built concurrently, idempotent.
create index concurrently if not exists derived_g1_projects on core.derived_items using gin ((attributes->'projects'))
    where derived_by = 'l3.extract' and generation = 'g1' and kind <> 'summary';

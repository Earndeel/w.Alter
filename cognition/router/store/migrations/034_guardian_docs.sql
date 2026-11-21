-- 2026-10-26: the guardian also keeps the generated reference (docs/reference) current, mechanically.
begin;
comment on column models.guardian_incidents.kind is
    'source_stale | source_error | provider_down | test_failure | cycle_failed | docs_stale (generated reference '
    'out of date: regenerated without a model).';
insert into models.schema_migrations (version) values ('034_guardian_docs') on conflict do nothing;
commit;

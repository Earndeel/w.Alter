-- Fiches de poste (2026-10-02): models are also judged on speed, agentic reliability, hallucination resistance,
-- context window and access, per job (orchestrator, agent worker). Context window comes from provider catalogues.
begin;
alter table models.canonical add column if not exists context_length int;
insert into models.schema_migrations (version) values ('015_postes') on conflict do nothing;
commit;

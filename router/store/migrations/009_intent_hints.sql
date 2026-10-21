-- What each task means for the intent classifier (Jev): plain definitions, from config/knowledge.json.
begin;
alter table models.tasks add column if not exists intent_hint text;
insert into models.schema_migrations (version) values ('009_intent_hints') on conflict do nothing;
commit;

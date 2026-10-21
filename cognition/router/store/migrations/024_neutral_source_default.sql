-- 2026-10-19 (software/instance split): declarations and verdicts come from the instance's owner, so the column
-- default no longer names a person. Rows already recorded keep their source.
alter table models.profiles alter column source set default 'owner';
alter table models.feedback alter column source set default 'owner';

insert into models.schema_migrations (version) values ('024_neutral_source_default') on conflict do nothing;

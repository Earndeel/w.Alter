-- A document that disappears from disk is marked, not dropped (its decisions too): review I4, 2026-11-14.
begin;
alter table devboard.documents add column if not exists removed_at timestamptz;
insert into devboard.migrations (version) values ('002_documents_removed') on conflict do nothing;
commit;

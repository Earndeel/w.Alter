-- Several accounts of one subscription provider (two Claude accounts, 2026-11-07, DECISIONS.md): each route names the
-- account (subscription id) it ran on, so quota use, rate-limit skips and fallbacks are traceable per account.
begin;
alter table models.exec_log add column if not exists account text;
comment on column models.exec_log.account is 'Subscription (config subscriptions.json id, e.g. anthropic-pro-2) whose account served this attempt when its provider has several accounts; null otherwise.';
insert into models.schema_migrations (version) values ('039_exec_log_account') on conflict do nothing;
commit;

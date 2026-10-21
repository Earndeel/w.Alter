-- A provider out of credit (OpenRouter balance) is worth one Telegram line; cleared when topped up.
begin;
alter table models.alerts drop constraint if exists alerts_kind_check;
alter table models.alerts add constraint alerts_kind_check
    check (kind in ('challenger', 'unranked', 'source_stale', 'top3', 'billing'));
insert into models.schema_migrations (version) values ('010_billing_alerts') on conflict do nothing;
commit;

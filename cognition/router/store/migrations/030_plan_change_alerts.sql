-- 2026-10-22: a billing e-mail (new plan, price change, cancellation) becomes a proposal on Telegram with buttons;
-- adopting it updates the owner's plans (research.plans.declared). Nothing changes without his button.
begin;
alter table models.alerts drop constraint if exists alerts_kind_check;
alter table models.alerts add constraint alerts_kind_check check (kind in ('challenger', 'unranked', 'source_stale',
    'top3', 'billing', 'tier', 'new_best', 'nerf', 'pareto', 'board_down', 'plan_change'));
insert into models.schema_migrations (version) values ('030_plan_change_alerts') on conflict do nothing;
commit;

-- 2026-11-20 (owner: « le router doit avoir un vrai agent intelligent qui s'occupe de comprendre les tenants et les
-- aboutissants »): the Router's advisor agent proposes consequences of a cycle or of an owner's choice as 'advice'
-- alerts (Telegram buttons; adopting applies one whitelisted action, analysis/advisor.py).
begin;
alter table models.alerts drop constraint if exists alerts_kind_check;
alter table models.alerts add constraint alerts_kind_check check (kind = any (array['challenger', 'unranked',
    'source_stale', 'top3', 'billing', 'tier', 'new_best', 'nerf', 'pareto', 'board_down', 'plan_change', 'advice']));
insert into models.schema_migrations (version) values ('043_alerts_advice') on conflict do nothing;
commit;

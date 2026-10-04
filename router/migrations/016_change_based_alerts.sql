-- 2026-10-04 (Monsieur): notify only on CHANGES between cycles — a new model above an active one, an active model
-- nerfed, a price drop that puts a model on the Pareto frontier. Short reference numbers for his replies.
begin;
alter table models.alerts add column if not exists ref int;
alter table models.alerts drop constraint if exists alerts_kind_check;
alter table models.alerts add constraint alerts_kind_check
    check (kind in ('challenger', 'unranked', 'source_stale', 'top3', 'billing', 'tier', 'new_best', 'nerf', 'pareto'));
update models.alerts set status = 'dismissed',
       verdict_note = '016: comparaison statique (orchestrateur) — pas une nouveauté, retirée à la demande de Monsieur'
where kind = 'tier' and role = 'orchestrator' and status in ('open', 'notified');
insert into models.schema_migrations (version) values ('016_change_based_alerts') on conflict do nothing;
commit;

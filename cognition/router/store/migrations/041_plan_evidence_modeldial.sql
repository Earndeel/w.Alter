-- 2026-11-16 (owner): ModelDial's measured quota of each subscription, model by model (plan/modeldial.py), is a source
-- of plan evidence of its own: origin 'modeldial', read by subscriptions.model_costs for the cost price per plan x model.
begin;
alter table models.plan_evidence drop constraint if exists plan_evidence_origin_check;
alter table models.plan_evidence add constraint plan_evidence_origin_check
    check (origin in ('web', 'email', 'owner', 'measure', 'modeldial'));
comment on column models.plan_evidence.origin is
    'web (research agent), email (billing mails), owner, measure (our meters), modeldial (ModelDial measured quotas, per model)';
insert into models.schema_migrations (version) values ('041_plan_evidence_modeldial') on conflict do nothing;
commit;

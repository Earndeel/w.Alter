-- 2026-10-02: (1) the three text tiers follow the owner's method (walter_router/tiers.py); when the nightly
-- computation designates another model than the declared tier, he gets one 'tier' alert and decides.
-- (2) specialised tasks: only the best model is useful (no #2/#3, no value ladder).
begin;
alter table models.alerts drop constraint if exists alerts_kind_check;
alter table models.alerts add constraint alerts_kind_check
    check (kind in ('challenger', 'unranked', 'source_stale', 'top3', 'billing', 'tier'));
update models.tasks set default_objective = 'best_available'
where task <> 'general' and default_objective <> 'tool';

create or replace view models.shortlist as
with s as (
    select model_id, task, 'top ' || level || ' #' || rank as why from models.selection
    where run_id = (select run_id from models.latest_run)
      and ((task = 'general' and level in ('L1', 'L2', 'L3')) or (task <> 'general' and level = 'best' and rank = 1))
    union all
    select pinned_model_id, task, 'favori ' || role from models.preferences where pinned_model_id is not null
    union all
    select k.model_id, k.interface, 'sans restriction' from models.catalog k
    left join models.profiles p using (model_id)
    where coalesce(p.content_policy, k.content_policy) <> 'standard'
)
select s.model_id, coalesce(c.display_name, s.model_id) as name,
       array_agg(distinct s.task order by s.task) as tasks, array_agg(distinct s.why order by s.why) as why
from s join models.canonical c using (model_id)
group by s.model_id, c.display_name;
insert into models.schema_migrations (version) values ('013_tiers_best_only') on conflict do nothing;
commit;

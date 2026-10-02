-- The router never needs the ~1 900 catalogued models: only Monsieur's favourites, the top picks per task and the
-- constrained (unrestricted) options. The full catalogue stays for watching (new top-3 entrants, overtaken
-- favourites, price changes) — this view is the short list the router actually chooses from.
begin;
create or replace view models.shortlist as
with s as (
    select model_id, task, 'top ' || level || ' #' || rank as why from models.selection
    where run_id = (select run_id from models.latest_run) and level <> 'frontier' and rank <= 3
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
insert into models.schema_migrations (version) values ('012_shortlist') on conflict do nothing;
commit;

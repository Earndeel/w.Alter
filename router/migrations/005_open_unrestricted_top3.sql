-- 2026-10-02, Monsieur:
--   * a place for open-weights models (text, image, video...) and for unrestricted models (uncensored /
--     abliterated fine-tunes, e.g. GLM 5.3 Flash Uncensored via Arnict AI on Hermes); the router can be asked for
--     a model under one of these constraints (`pick --require unrestricted|open_weights`). An unrestricted
--     fine-tune is rarely benchmarked: it inherits its base model's score, flagged as an estimate.
--   * relevant notifications only: a new model is reported when it enters the top 3 of a leaderboard of a domain
--     Monsieur watches (alert kind 'top3'); unranked releases are recorded but never sent.
begin;
alter table models.canonical add column if not exists open_weights boolean;          -- null = unknown
alter table models.canonical add column if not exists license text;
alter table models.canonical add column if not exists license_source text;
alter table models.canonical add column if not exists content_policy text not null default 'standard';
alter table models.canonical drop constraint if exists canonical_content_policy_check;
alter table models.canonical add constraint canonical_content_policy_check
    check (content_policy in ('standard', 'unrestricted'));
alter table models.canonical add column if not exists base_model_id text;            -- fine-tune -> base model

alter table models.alerts drop constraint if exists alerts_kind_check;
alter table models.alerts add constraint alerts_kind_check
    check (kind in ('challenger', 'unranked', 'source_stale', 'top3'));

create or replace view models.model_scores as
select model_id, jsonb_object_agg(benchmark || ':' || task, score) as scores
from (select b.model_id, b.benchmark, b.task, max(b.score) as score
      from models.benchmarks b join models.latest_snapshots s using (snapshot_id) group by 1, 2, 3) x
group by model_id;

create or replace view models.catalog as
with o as (
    select o.* from models.offers o join models.latest_snapshots s using (snapshot_id)
), g as (
    select model_id, interface,
           array_agg(distinct provider order by provider) as providers,
           min(norm_price) filter (where offer_kind = 'generation') as price_min,
           max(norm_price) filter (where offer_kind = 'generation') as price_max,
           mode() within group (order by norm_unit) filter (where offer_kind = 'generation' and norm_price is not null)
               as price_unit,
           array_agg(distinct resolution) filter (where offer_kind = 'generation' and resolution is not null) as resolutions,
           min(provider_created) as released,
           count(*) as offers
    from o group by model_id, interface
), m as (
    select model_id, interface, array_agg(distinct mode order by mode) as modes
    from o, unnest(o.modes) as mode where o.offer_kind = 'generation' group by model_id, interface
)
select g.model_id, coalesce(c.display_name, g.model_id) as name, g.interface, coalesce(m.modes, '{}') as modes,
       g.providers, g.price_min, g.price_max, g.price_unit, coalesce(g.resolutions, '{}') as resolutions, g.released,
       g.offers, coalesce(b.scores, '{}') as scores, b.scores is not null as ranked,
       c.open_weights, c.license, c.content_policy, c.base_model_id
from g join models.canonical c using (model_id)
left join m using (model_id, interface)
left join models.model_scores b using (model_id);

-- Open-weights and unrestricted models that can be called today, with their (or their base model's) scores.
create or replace view models.open_models as
select k.*, coalesce(nullif(k.scores, '{}'), bb.scores, '{}') as scores_or_base,
       k.scores = '{}' and bb.scores is not null as score_from_base
from models.catalog k
left join models.model_scores bb on bb.model_id = k.base_model_id
where k.open_weights or k.content_policy = 'unrestricted';

insert into models.schema_migrations (version) values ('005_open_unrestricted_top3') on conflict do nothing;
commit;

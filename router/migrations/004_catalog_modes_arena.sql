-- Media catalogue, organised per model (2026-10-02, Monsieur):
--   * every offer says what it sells: generation mode(s) t2i/i2i/t2v/i2v/r2v/v2v, output resolution, audio, and a
--     price in the comparable unit (video per second, image per image) -> models.offers new columns;
--   * a readable name per model (models.canonical.display_name, best source wins);
--   * one view models.catalog = one row per model and interface: modes, providers, price range, resolutions,
--     release date and every leaderboard score (AA, AA multimodal, Design Arena, Arena.ai);
--   * Arena.ai joins the leaderboards: a task can be judged on several boards (models.task_benchmarks), a favourite
--     is overtaken when a model beats it on any of them;
--   * tasks know which generation modes they need (an image edit is priced on i2i SKUs, not t2i).
begin;
alter table models.offers add column if not exists offer_kind text not null default 'generation';
alter table models.offers drop constraint if exists offers_offer_kind_check;
alter table models.offers add constraint offers_offer_kind_check check (offer_kind in ('generation', 'fee', 'tool'));
alter table models.offers add column if not exists modes text[] not null default '{}';
alter table models.offers add column if not exists resolution text;
alter table models.offers add column if not exists audio boolean;
alter table models.offers add column if not exists norm_price double precision;   -- USD in norm_unit
alter table models.offers add column if not exists norm_unit text;                 -- per second | per image | ...

alter table models.canonical add column if not exists display_name text;
alter table models.canonical add column if not exists display_source text;

alter table models.tasks add column if not exists modes text[] not null default '{}';

create table if not exists models.task_benchmarks (
    task       text not null references models.tasks on delete cascade,
    benchmark  text not null,                  -- aa_intelligence | aa_mm | da_models | da_agents | arena
    bench_task text not null,                  -- the board inside that benchmark
    is_primary boolean not null default false, -- the board used to rank and price the task
    primary key (task, benchmark, bench_task)
);

insert into models.tasks (task, label, interface, quality_benchmark, quality_task, default_objective, description) values
  ('image_edit', 'Retouche / édition d''image', 'image', 'arena', 'image_edit', 'best_available', 'Arena Image Edit'),
  ('video_edit', 'Édition de vidéo',            'video', 'arena', 'video_edit', 'value',          'Arena Video Edit'),
  ('vision',     'Analyse d''image',            'chat',  'arena', 'vision',     'value',          'Arena Vision'),
  ('document',   'Analyse de document / PDF',   'chat',  'arena', 'document',   'value',          'Arena Document')
on conflict (task) do nothing;

update models.tasks set modes = '{t2i}' where task in ('text_to_image', 'logo', 'graphic_design');
update models.tasks set modes = '{i2i}' where task = 'image_edit';
update models.tasks set modes = '{t2v}' where task = 'text_to_video';
update models.tasks set modes = '{i2v}' where task = 'image_to_video';
update models.tasks set modes = '{v2v}' where task = 'video_edit';

insert into models.task_benchmarks (task, benchmark, bench_task, is_primary)
select task, quality_benchmark, quality_task, true from models.tasks where quality_benchmark is not null
on conflict do nothing;
insert into models.task_benchmarks (task, benchmark, bench_task) values
  ('general',        'arena', 'text'),
  ('general',        'arena', 'text_french'),
  ('frontend',       'arena', 'webdev'),
  ('ui_component',   'arena', 'webdev'),
  ('fullstack',      'arena', 'webdev'),
  ('text_to_image',  'arena', 'text_to_image'),
  ('text_to_video',  'arena', 'text_to_video'),
  ('image_to_video', 'arena', 'image_to_video')
on conflict do nothing;

create or replace view models.latest_snapshots as
    select distinct on (kind) kind, snapshot_id, fetched_at from models.snapshots
    order by kind, fetched_at desc, snapshot_id desc;

-- One row per model and interface, from the latest snapshot of every source.
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
), b as (
    select model_id, jsonb_object_agg(benchmark || ':' || task, score) as scores
    from (select b.model_id, b.benchmark, b.task, max(b.score) as score
          from models.benchmarks b join models.latest_snapshots s using (snapshot_id) group by 1, 2, 3) x
    group by model_id
)
select g.model_id, coalesce(c.display_name, g.model_id) as name, g.interface, coalesce(m.modes, '{}') as modes,
       g.providers, g.price_min, g.price_max, g.price_unit, coalesce(g.resolutions, '{}') as resolutions, g.released,
       g.offers, coalesce(b.scores, '{}') as scores, b.scores is not null as ranked
from g join models.canonical c using (model_id)
left join m using (model_id, interface)
left join b using (model_id);

alter table models.alerts drop constraint if exists alerts_kind_check;
alter table models.alerts add constraint alerts_kind_check check (kind in ('challenger', 'unranked', 'source_stale'));

insert into models.schema_migrations (version) values ('004_catalog_modes_arena') on conflict do nothing;
commit;

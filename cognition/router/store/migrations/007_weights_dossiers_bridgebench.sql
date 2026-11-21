-- 2026-10-02: BridgeBench joins the leaderboards (vibe-coding benchmark, 10 axes); every board of a task gets a
-- weight, and the router reads one pre-computed JSON "dossier" per task (roles, profiles, weighted candidates,
-- routes) instead of re-deriving everything at request time.
begin;
alter table models.task_benchmarks add column if not exists weight real not null default 1.0;
alter table models.task_benchmarks add column if not exists note text;

create table if not exists models.dossiers (
    run_id   bigint not null references models.runs on delete cascade,
    task     text not null references models.tasks,
    doc      jsonb not null,
    built_at timestamptz not null default now(),
    primary key (run_id, task)
);
create or replace view models.latest_dossiers as
    select d.task, d.doc, d.built_at from models.dossiers d join models.latest_run r using (run_id);

insert into models.tasks (task, label, interface, quality_benchmark, quality_task, default_objective, description) values
  ('coding', 'Code / back-end / agentique', 'chat', 'arena', 'text_coding', 'best_available',
   'Arena coding + BridgeBench (vibe coding) + Arena webdev')
on conflict (task) do nothing;

-- Board weights per task (sum ~1 per task; reliability and coverage are applied on top at scoring time).
insert into models.task_benchmarks (task, benchmark, bench_task, is_primary, weight, note) values
  ('general',        'bridgebench', 'overall',   false, 0.10, 'BridgeBench global'),
  ('frontend',       'bridgebench', 'frontend',  false, 0.25, null),
  ('ui_component',   'bridgebench', 'frontend',  false, 0.25, null),
  ('3d',             'arena',       'webdev',    false, 0.25, null),
  ('3d',             'bridgebench', 'frontend',  false, 0.15, null),
  ('gamedev',        'arena',       'webdev',    false, 0.25, null),
  ('gamedev',        'bridgebench', 'frontend',  false, 0.15, null),
  ('dataviz',        'arena',       'webdev',    false, 0.25, null),
  ('dataviz',        'bridgebench', 'frontend',  false, 0.15, null),
  ('svg',            'arena',       'webdev',    false, 0.25, null),
  ('fullstack',      'bridgebench', 'overall',   false, 0.20, null),
  ('fullstack',      'bridgebench', 'backend',   false, 0.20, null),
  ('mobile_app',     'arena',       'webdev',    false, 0.20, null),
  ('mobile_app',     'bridgebench', 'overall',   false, 0.20, null),
  ('coding',         'arena',       'text_coding', true, 0.30, null),
  ('coding',         'arena',       'webdev',    false, 0.20, null),
  ('coding',         'bridgebench', 'overall',   false, 0.35, null),
  ('coding',         'bridgebench', 'backend',   false, 0.15, null),
  ('logo',           'arena',       'text_to_image', false, 0.30, null),
  ('graphic_design', 'arena',       'text_to_image', false, 0.30, null)
on conflict (task, benchmark, bench_task) do update set weight = excluded.weight, note = excluded.note;

update models.task_benchmarks set weight = case
    when task = 'general' and benchmark = 'aa_intelligence' then 0.50
    when task = 'general' and bench_task = 'text' then 0.20
    when task = 'general' and bench_task = 'text_french' then 0.20
    when task in ('frontend', 'ui_component') and benchmark = 'da_models' then 0.45
    when task in ('frontend', 'ui_component', 'fullstack') and bench_task = 'webdev' then 0.30
    when task in ('3d', 'gamedev', 'dataviz', 'svg') and benchmark = 'da_models' then 0.60
    when task = 'svg' and bench_task = 'webdev' then 0.40
    when task = 'fullstack' and benchmark = 'da_agents' then 0.40
    when task = 'mobile_app' and benchmark = 'da_agents' then 0.60
    when task in ('logo', 'graphic_design') and benchmark = 'da_models' then 0.70
    when task in ('text_to_image', 'text_to_video', 'image_to_video') then 0.50
    else weight end;
update models.task_benchmarks set weight = 0.20 where task = 'fullstack' and bench_task = 'webdev';

insert into models.schema_migrations (version) values ('007_weights_dossiers_bridgebench') on conflict do nothing;
commit;

-- Walter Memory — journal of applied migrations (2026-10-29, Walter Clean), like the Router's models.schema_migrations.
-- `walter-memory migrate` records each file here: mode 'applied' (run by the runner) or 'baseline' (already applied by
-- hand on the first instance before the runner existed: recorded, never re-run).
create table if not exists core.schema_migrations (
    version    text primary key,                         -- file name, e.g. 018_runs_episodes.sql
    sha256     text not null,                            -- content of the file when it was recorded
    mode       text not null check (mode in ('applied', 'baseline')),
    applied_at timestamptz not null default now()
);
comment on table core.schema_migrations is 'Walter Memory migrations recorded by walter-memory migrate (applied or baseline).';

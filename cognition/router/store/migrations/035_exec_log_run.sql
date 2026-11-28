-- Walter Run Plane (2026-10-27, DECISIONS.md): each model execution names the run and task it served, so a run can be
-- rebuilt from the tables (walter-memory runs show). Nullable: executions outside a run keep working unchanged.
begin;
alter table models.exec_log add column if not exists run_id uuid;
alter table models.exec_log add column if not exists task_id uuid;
comment on column models.exec_log.run_id is 'Walter run (runs.runs.run_id) this execution served, from WALTER_RUN_ID; null outside a run.';
comment on column models.exec_log.task_id is 'Sub-agent task (runs.tasks.task_id) this execution served (walter_run); null otherwise.';
create index if not exists exec_log_run on models.exec_log (run_id) where run_id is not null;
insert into models.schema_migrations (version) values ('035_exec_log_run') on conflict do nothing;
commit;

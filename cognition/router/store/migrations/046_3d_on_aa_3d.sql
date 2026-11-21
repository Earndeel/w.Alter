-- 2026-11-21 (owner): « pour la 3D garde le benchmark index AA plutôt ». 3D is ranked on the Artificial Analysis 3D
-- arena alone (aa_eval / aa_3d); its Design Arena board is still collected but no longer weighs nor raises proposals.
begin;
delete from models.task_benchmarks where task = '3d' and not (benchmark = 'aa_eval' and bench_task = 'aa_3d');
insert into models.task_benchmarks (task, benchmark, bench_task, weight, is_primary)
  values ('3d', 'aa_eval', 'aa_3d', 1.0, true)
  on conflict (task, benchmark, bench_task) do update set weight = 1.0, is_primary = true;
update models.tasks set description = 'Artificial Analysis 3D Arena'
  where task = '3d';
insert into models.schema_migrations (version) values ('046_3d_on_aa_3d') on conflict do nothing;
commit;

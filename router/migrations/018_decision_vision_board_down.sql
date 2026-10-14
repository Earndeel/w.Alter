-- 2026-10-14 (Monsieur): (1) a decision category for image inputs (fast web navigation, bulk image processing):
-- same AA Decision Index, restricted to decision models that read images. (2) an alert when a leaderboard can no
-- longer be read (Arena image-edit stopped returning rows on 2026-10-10 and nobody knew).
begin;
insert into models.tasks (task, label, interface, quality_benchmark, quality_task, default_objective, description, modes)
values ('decision_vision', 'Modèle de décision avec image (navigation, traitement d''images en masse)', 'decisions',
        'aa_decision', 'decision', 'best_available',
        'Decision models that also read images (OpenRouter input modalities). AA Decision Index has no vision test yet: '
        'ranked on the text index, filtered on image input.', '{image}')
on conflict (task) do nothing;
insert into models.task_benchmarks (task, benchmark, bench_task, is_primary, weight, note)
values ('decision_vision', 'aa_decision', 'decision', true, 1.0, 'AA Decision Index v1.0 (no vision eval yet)')
on conflict do nothing;
alter table models.alerts drop constraint if exists alerts_kind_check;
alter table models.alerts add constraint alerts_kind_check
    check (kind in ('challenger', 'unranked', 'source_stale', 'top3', 'billing', 'tier', 'new_best', 'nerf', 'pareto',
                    'board_down'));
insert into models.schema_migrations (version) values ('018_decision_vision_board_down') on conflict do nothing;
commit;

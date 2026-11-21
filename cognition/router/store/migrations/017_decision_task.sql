-- 2026-10-14: AA Decision Index v1.0 (2026-10-13) joins the leaderboards. 'decision' is an INTERNAL task: the model
-- that understands the owner's intent and routes it (intent.py) and decides on environmental inputs (V3 triage).
-- Interface 'decisions' (typed answers with probabilities, OpenRouter Decisions API / Workers AI); never offered to
-- the intent classifier as a task family, never shown in the task list given to agents.
begin;
insert into models.tasks (task, label, interface, quality_benchmark, quality_task, default_objective, description)
values ('decision', 'Modèle de décision (routage d''intention, tri)', 'decisions', 'aa_decision', 'decision',
        'best_available',
        'AA Decision Index: classification, tool-calling decisions (When2Call), knowledge with "I don''t know" '
        '(non-hallucination), reasoning; speed and cost per 1M tasks')
on conflict (task) do update set quality_benchmark = excluded.quality_benchmark, quality_task = excluded.quality_task,
    interface = excluded.interface, description = excluded.description;
insert into models.task_benchmarks (task, benchmark, bench_task, is_primary, weight, note)
values ('decision', 'aa_decision', 'decision', true, 1.0, 'AA Decision Index v1.0')
on conflict do nothing;
insert into models.schema_migrations (version) values ('017_decision_task') on conflict do nothing;
commit;

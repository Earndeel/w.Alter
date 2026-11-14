-- 2026-11-14: ops/devboard reads agent sessions and the decision journal to keep the development board up to date
-- (chantiers, their state, approvals, which decision replaces which). One internal poste of its own, so its pin never
-- moves another module's model; never offered to the intent classifier.
begin;
insert into models.tasks (task, label, interface, quality_benchmark, quality_task, default_objective, description,
                          requirements, internal, consumers) values
  ('devboard_reading', 'Lecture du développement (tableau)', 'chat', 'aa_intelligence', 'intelligence', 'best_available',
   'Lire un condensé de session d''agent ou une décision et en tirer chantiers, états, accords et remplacements, en JSON fidèle avec preuves.',
   '{"structured_output": true, "min_context": 128000}', true, 'ops/devboard')
on conflict (task) do update set label = excluded.label, interface = excluded.interface,
    quality_benchmark = excluded.quality_benchmark, quality_task = excluded.quality_task,
    default_objective = excluded.default_objective, description = excluded.description,
    requirements = excluded.requirements, internal = excluded.internal, consumers = excluded.consumers;
insert into models.schema_migrations (version) values ('040_devboard_reading') on conflict do nothing;
commit;

-- 2026-10-22 (owner: « il y a aussi des index pour l'ingénierie etc. sur AA »): AA's domain indexes
-- (artificialanalysis.ai/indexes) rank professions; each becomes a task or reinforces one. They cover AA's frontier
-- models only (19-27), so the composite's evidence shrinkage keeps a lone top score from deciding alone.
begin;
insert into models.tasks (task, label, interface, quality_benchmark, quality_task, default_objective, description,
                          intent_hint, requirements, internal) values
  ('engineering', 'Ingénierie', 'chat', 'aa_eval', 'idx_engineering', 'best_available',
   'Travail d''ingénieur : analyse de conception, calculs techniques, normes, documentation technique. AA Engineering Index.',
   'Question d''ingénieur : conception mécanique, électrique ou civile, calcul technique, normes, documentation technique (pas du code logiciel)',
   '{}', false),
  ('finance', 'Finance / comptabilité / économie', 'chat', 'aa_eval', 'idx_finance', 'best_available',
   'Comptabilité, analyse financière, fiscalité, prévisions et analyse économique quantitative. AA Finance & Accounting et Economics Index.',
   'Finance, comptabilité ou économie : bilan, compte de résultat, fiscalité, valorisation, budget, prévision économique',
   '{}', false),
  ('strategy', 'Stratégie / conseil / opérations', 'chat', 'aa_eval', 'idx_strategy_ops', 'best_available',
   'Travail de consultant : stratégie d''entreprise, organisation, opérations, analyse de marché. AA Strategy & Ops Index.',
   'Conseil en stratégie ou opérations d''entreprise : business plan, analyse de marché, organisation, processus, décision de direction',
   '{}', false),
  ('cybersecurity', 'Cybersécurité', 'chat', 'aa_eval', 'cyber', 'best_available',
   'Sécurité informatique : audit de code, vulnérabilités, analyse d''incident, durcissement. AA Cyber Index.',
   'Cybersécurité : vulnérabilité, audit de sécurité, pentest autorisé, analyse d''attaque, durcissement d''un système',
   '{}', false)
on conflict (task) do update set label = excluded.label, interface = excluded.interface,
    quality_benchmark = excluded.quality_benchmark, quality_task = excluded.quality_task,
    default_objective = excluded.default_objective, description = excluded.description,
    intent_hint = excluded.intent_hint, requirements = excluded.requirements, internal = excluded.internal;

insert into models.task_benchmarks (task, benchmark, bench_task, is_primary, weight, note) values
  ('engineering', 'aa_eval', 'idx_engineering', true, 1.0, 'AA Engineering Index'),
  ('finance', 'aa_eval', 'idx_finance', true, 0.7, 'AA Finance & Accounting Index'),
  ('finance', 'aa_eval', 'idx_economics', false, 0.3, 'AA Economics Index'),
  ('strategy', 'aa_eval', 'idx_strategy_ops', true, 1.0, 'AA Strategy & Ops Index'),
  ('cybersecurity', 'aa_eval', 'cyber', true, 1.0, 'AA Cyber Index'),
  ('medical', 'aa_eval', 'idx_medical', true, 0.5, 'AA Healthcare & Medical Index'),
  ('legal', 'aa_eval', 'idx_legal', true, 0.6, 'AA Legal Index')
on conflict do nothing;
update models.task_benchmarks set is_primary = false, weight = 0.3 where task = 'medical' and bench_task = 'healthbench_pro';
update models.task_benchmarks set weight = 0.2 where task = 'medical' and bench_task = 'healthbench';
update models.task_benchmarks set is_primary = false, weight = 0.4 where task = 'legal' and bench_task = 'harvey_lab';
update models.tasks set quality_task = 'idx_medical',
    description = 'Questions de santé : symptômes, maladies, médicaments, lecture de résultats. AA Healthcare & Medical Index + HealthBench.'
  where task = 'medical';
update models.tasks set quality_task = 'idx_legal',
    description = 'Questions juridiques et travail d''avocat : contrats, litiges, réglementation. AA Legal Index + Harvey LAB.'
  where task = 'legal';
insert into models.schema_migrations (version) values ('026_aa_domain_indexes') on conflict do nothing;
commit;

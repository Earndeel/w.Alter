-- 2026-10-21 (owner): research goes deep — specialised domains from AA evaluations (medical, legal, science, long
-- context), writing quality (Arena creative writing), music (AA Music), and AA evaluations reinforcing 3D and vision.
-- New tasks start without a pin: the router picks the best callable model; any later change is only proposed.
begin;
insert into models.tasks (task, label, interface, quality_benchmark, quality_task, default_objective, description,
                          intent_hint, requirements, internal) values
  ('medical', 'Santé / médical', 'chat', 'aa_eval', 'healthbench_pro', 'best_available',
   'Questions de santé : symptômes, maladies, médicaments, lecture de résultats. Classé sur HealthBench (AA).',
   'Question de santé ou médicale : symptômes, maladie, médicament, posologie, résultats d''analyse, conseil médical',
   '{}', false),
  ('legal', 'Juridique / droit', 'chat', 'aa_eval', 'harvey_lab', 'best_available',
   'Questions juridiques et travail d''avocat : contrats, litiges, réglementation, conformité. Classé sur Harvey LAB (AA).',
   'Question juridique : droit, contrat, clause, litige, réglementation, conformité, démarche légale',
   '{}', false),
  ('science', 'Sciences / recherche avancée', 'chat', 'aa_eval', 'critpt', 'best_available',
   'Problèmes scientifiques de niveau recherche : physique, chimie, biologie, mathématiques, calcul scientifique.',
   'Problème scientifique avancé : physique, chimie, biologie, mathématiques de niveau recherche, démonstration, calcul scientifique',
   '{}', false),
  ('long_context', 'Long contexte (très longs documents)', 'chat', 'aa_eval', 'lcr', 'best_available',
   'Raisonner sur un très long contexte : livre, base documentaire, plusieurs gros documents, long historique.',
   'Travailler sur un très long texte ou plusieurs gros documents à la fois : livre entier, base documentaire, très long historique',
   '{}', false),
  ('writing', 'Rédaction / qualité d''écriture', 'chat', 'arena', 'text_creative', 'best_available',
   'Textes soignés : articles, histoires, discours, textes créatifs, réécriture de style. Classé sur Arena (écriture créative, français).',
   'Écriture créative ou littéraire exigeante : histoire, poème, discours, article de fond, réécriture de style (pas un simple mail, message ou résumé)',
   '{}', false)
on conflict (task) do update set label = excluded.label, interface = excluded.interface,
    quality_benchmark = excluded.quality_benchmark, quality_task = excluded.quality_task,
    default_objective = excluded.default_objective, description = excluded.description,
    intent_hint = excluded.intent_hint, requirements = excluded.requirements, internal = excluded.internal;

update models.tasks set quality_benchmark = 'aa_mm', quality_task = 'music_vocals',
    description = coalesce(description, '') || ' Classé sur AA Music (chant et instrumental).'
  where task = 'music' and quality_benchmark is null;

insert into models.task_benchmarks (task, benchmark, bench_task, is_primary, weight, note) values
  ('medical', 'aa_eval', 'healthbench_pro', true, 0.6, 'HealthBench Professional : cas cliniques de professionnels'),
  ('medical', 'aa_eval', 'healthbench', false, 0.4, 'HealthBench : questions de santé du grand public'),
  ('legal', 'aa_eval', 'harvey_lab', true, 1.0, 'Harvey LAB : tâches réelles d''avocats (critères tous validés)'),
  ('science', 'aa_eval', 'critpt', true, 0.35, 'CritPt : physique de niveau recherche'),
  ('science', 'aa_eval', 'gpqa', false, 0.35, 'GPQA Diamond : questions de doctorat'),
  ('science', 'aa_eval', 'scicode', false, 0.15, 'SciCode : calcul scientifique'),
  ('science', 'aa_eval', 'hle', false, 0.15, 'Humanity''s Last Exam'),
  ('long_context', 'aa_eval', 'lcr', true, 1.0, 'AA-LCR : raisonnement sur ~100k tokens de documents'),
  ('writing', 'arena', 'text_creative', true, 0.6, 'Arena écriture créative (votes humains)'),
  ('writing', 'arena', 'text_french', false, 0.4, 'le propriétaire écrit en français'),
  ('music', 'aa_mm', 'music_vocals', true, 0.5, 'AA Music chant'),
  ('music', 'aa_mm', 'music_instrumental', false, 0.5, 'AA Music instrumental'),
  ('3d', 'aa_eval', 'aa_3d', false, 0.2, 'AA-3D : scènes 3D construites par des agents'),
  ('vision', 'aa_eval', 'mmmu_pro', false, 0.4, 'MMMU-Pro : raisonnement sur images')
on conflict do nothing;
-- 3D and vision keep their human-preference boards first; AA evaluations join them
update models.task_benchmarks set weight = 0.5 where task = '3d' and benchmark = 'da_models' and bench_task = '3d';
update models.task_benchmarks set weight = 0.2 where task = '3d' and benchmark = 'arena' and bench_task = 'webdev';
update models.task_benchmarks set weight = 0.1 where task = '3d' and benchmark = 'bridgebench' and bench_task = 'frontend';
update models.task_benchmarks set weight = 0.6 where task = 'vision' and benchmark = 'arena' and bench_task = 'vision';

comment on table models.task_benchmarks is 'Boards that rank each task and their weights (scoring.composite); shown under each task on the library page. Sources: AA (intelligence, evaluations aa_eval, media aa_mm, decision, STT), Arena, Design Arena, BridgeBench, Agentset, MTEB';
insert into models.schema_migrations (version) values ('025_specialised_tasks_music') on conflict do nothing;
commit;

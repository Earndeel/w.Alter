-- 2026-11-21 (owner): « les modèles spécialisés doivent se référer à un benchmark ; dans ce cas c'est
-- https://artificialanalysis.ai/indexes/healthcare-and-medical ». A specialised task with an AA domain index is ranked
-- on that index alone: the secondary boards (HealthBench, HealthBench Professional, Economics, Harvey LAB) no longer
-- weigh nor raise proposals (a model scored only there — GPT-6 Astra in medical — is not ranked). Their scores stay
-- collected. Same rule already held for engineering and strategy.
begin;
delete from models.task_benchmarks where (task, bench_task) in
    (('medical', 'healthbench'), ('medical', 'healthbench_pro'), ('finance', 'idx_economics'), ('legal', 'harvey_lab'));
update models.task_benchmarks set is_primary = true, weight = 1.0
  where (task, bench_task) in (('medical', 'idx_medical'), ('finance', 'idx_finance'), ('legal', 'idx_legal'));
update models.tasks set description = 'Questions de santé : symptômes, maladies, médicaments, lecture de résultats. Référence : AA Healthcare & Medical Index.'
  where task = 'medical';
update models.tasks set description = 'Questions juridiques et travail d''avocat : contrats, litiges, réglementation. Référence : AA Legal Index.'
  where task = 'legal';
update models.tasks set description = 'Comptabilité, analyse financière, fiscalité, prévisions et analyse économique quantitative. Référence : AA Finance & Accounting Index.'
  where task = 'finance';
insert into models.schema_migrations (version) values ('044_specialists_one_reference') on conflict do nothing;
commit;

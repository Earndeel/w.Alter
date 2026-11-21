-- 2026-10-29 (Walter Clean): poste texts shipped with the software name no person. Three texts written for the first
-- instance's owner become neutral (and "Hindsight", retired on 2026-10-19, is no longer named). Selection unchanged.
BEGIN;
update models.tasks set description = 'Transcrire les messages vocaux du propriétaire, dans sa langue : fidélité d''abord (AA-WER, mesuré en anglais : AA ne publie pas de résultat français), puis vitesse. Modèles de transcription et modèles de chat qui entendent l''audio.'
 where task = 'stt';
update models.tasks set description = 'Vecteurs de la mémoire : qualité de recherche (ELO Agentset) et recherche en français (MTEB MIRACL fr) ; seuls les modèles mesurés sur le classement principal sont rangés (revectoriser ne se décide pas sur un seul test). Changer de modèle oblige à revectoriser toute la banque : jamais sans l''accord du propriétaire.'
 where task = 'embeddings';
update models.task_benchmarks set note = 'Classement en français : la langue de l''instance'
 where task = 'voice_assist' and benchmark = 'arena' and bench_task = 'text_french';

insert into models.schema_migrations (version) values ('037_neutral_task_texts') on conflict do nothing;
COMMIT;

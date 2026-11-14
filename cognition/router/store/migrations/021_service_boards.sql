-- 2026-10-16: « il faudra rajouter le reranking, embedding et STT dans walter router ». The three service
-- postes of migration 020 get measured leaderboards and are ranked like any task (task_benchmarks weights ->
-- scoring.composite, dossiers, challenger alerts). They stay PINNED on the models in use: a better measured model is
-- only proposed (challenger, « Changer » button), never switched automatically.
--
-- Boards (scores stored "higher = better"; the raw measure stays in benchmarks.extra):
--   aa_stt:wer            AA Speech-to-Text, 100 - AA-WER % (English datasets; AA publishes no French result)
--   aa_stt:speed          AA STT speed factor (x real time)
--   agentset:rerank       Agentset reranker ELO (pairwise, RAG retrieval) ; agentset:rerank_speed = 1000 / latency ms
--   agentset:embeddings   Agentset embedding ELO ; mteb:retrieval_fr = MTEB MIRACL-HN French nDCG@10 x100
-- Interfaces follow the offers (OpenRouter output modality): stt -> 'transcription' (dedicated STT models + chat
-- models that hear audio), embeddings -> 'embedding'. Before, stt sat on 'audio' (the TTS interface) and embeddings on
-- 'embeddings', which no offer carried: neither could rank a callable candidate.
begin;
update models.tasks set interface = 'transcription', quality_benchmark = 'aa_stt', quality_task = 'wer',
    description = 'Transcrire les messages vocaux du propriétaire (français) : fidélité d''abord (AA-WER, mesuré en anglais : '
                  'AA ne publie pas de résultat français), puis vitesse. Modèles de transcription et modèles de chat qui '
                  'entendent l''audio.',
    requirements = requirements || '{"on_change": "Adopter un modèle de transcription dédié (Whisper, MAI, Scribe…) : le plugin Hermes gemini-stt appelle aujourd''hui chat/completions avec input_audio ; il devra appeler l''API de transcription d''OpenRouter."}'
where task = 'stt';
update models.tasks set quality_benchmark = 'agentset', quality_task = 'rerank',
    description = 'Réordonner les souvenirs trouvés avant de les donner au modèle (rappel mémoire, voix) : qualité de '
                  'classement (ELO Agentset) puis latence ; au-delà de 0,7 s mesurés, un modèle est exclu (budget du rappel vocal).',
    requirements = requirements || '{"on_change": "Hindsight garde son reranker dans le drop-in statique 20-reranker-fallback.conf : à modifier à la main après adoption ; walter-memory et walter-voice-memory suivent pick rerank."}'
where task = 'rerank';
update models.tasks set interface = 'embedding', quality_benchmark = 'agentset', quality_task = 'embeddings',
    description = 'Vecteurs de la mémoire Hindsight : qualité de recherche (ELO Agentset) et recherche en français (MTEB '
                  'MIRACL fr) ; seuls les modèles mesurés sur le classement principal sont rangés (revectoriser '
                  'ne se décide pas sur un seul test). Changer de modèle oblige à revectoriser toute la banque : '
                  'jamais sans le propriétaire.',
    requirements = requirements || '{"require_primary": true, "on_change": "Changer de modèle d''embeddings = revectoriser toutes les banques Hindsight (walter, walter-shadow) : opération lourde, à planifier avec the owner. Hindsight garde son modèle dans sa configuration tant que ce n''est pas fait (walter-voice-memory n''est pas concerné : vecteurs locaux)."}'
where task = 'embeddings';

insert into models.task_benchmarks (task, benchmark, bench_task, is_primary, weight, note) values
  ('stt', 'aa_stt', 'wer', true, 0.75, 'fidélité de transcription (AA-WER, anglais)'),
  ('stt', 'aa_stt', 'speed', false, 0.25, 'vitesse (facteur temps réel) : messages vocaux transcrits sans attendre'),
  ('rerank', 'agentset', 'rerank', true, 0.7, 'qualité de classement RAG (ELO par paires)'),
  ('rerank', 'agentset', 'rerank_speed', false, 0.3, 'latence : budget du rappel vocal 0,7 s'),
  ('embeddings', 'agentset', 'embeddings', true, 0.5, 'qualité de recherche RAG (ELO par paires)'),
  ('embeddings', 'mteb', 'retrieval_fr', false, 0.5, 'recherche en français (MIRACL fr, nDCG@10)')
on conflict (task, benchmark, bench_task) do update set is_primary = excluded.is_primary, weight = excluded.weight,
    note = excluded.note;

insert into models.schema_migrations (version) values ('021_service_boards') on conflict do nothing;
commit;

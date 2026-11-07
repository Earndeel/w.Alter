-- 2026-10-16: every W.Alter module that uses AI goes through Walter Router's library, so each use gets the
-- best model of its task and follows the router's updates (48 h cycle, the owner's pins). Before this, Hermes context
-- compression, Hindsight, the voice router, walter-memory's L3 synthesis and the profile compiler had Gemini ids
-- written in their own config and called Google AI Studio directly.
--
-- Internal postes = tasks the modules call, never offered to the intent classifier (internal = true).
--   objective 'level'  : a background text job follows one of the owner's text tiers (knowledge.json "levels",
--                        his method, adopted by him) — requirements.level; requirements.min_context filters the tier.
--   best_available     : ranked on the task's boards like any specialised task (voice_assist: speed first).
--   no board (stt, embeddings): the owner's pin only, until a leaderboard is collected for it.
begin;
alter table models.tasks add column if not exists requirements jsonb not null default '{}';
alter table models.tasks add column if not exists internal boolean not null default false;
alter table models.tasks add column if not exists consumers text;
alter table models.tasks drop constraint if exists tasks_default_objective_check;
alter table models.tasks add constraint tasks_default_objective_check
    check (default_objective in ('value', 'best_available', 'tool', 'level'));

insert into models.tasks (task, label, interface, quality_benchmark, quality_task, default_objective, description,
                          requirements, internal, consumers) values
  ('summarization', 'Résumé / compression de contexte', 'chat', 'aa_intelligence', 'intelligence', 'level',
   'Résumer fidèlement un long contexte (conversation, journal) sans rien inventer : tâche de fond, volume élevé.',
   '{"level": "L1", "min_context": 256000}',
   true, 'Hermes auxiliary.compression (walter-compress) ; walter-memory l3.conversation_summary'),
  ('memory_extraction', 'Extraction mémoire structurée', 'chat', 'aa_intelligence', 'intelligence', 'level',
   'Extraire faits, entités, préférences et liens d''un texte en JSON fidèle (rétention, consolidation, profil).',
   '{"level": "L1", "min_context": 128000, "structured_output": true}',
   true, 'Hindsight retain / consolidation / reflect ; user_profile_compiler'),
  ('voice_assist', 'Aide texte pendant un appel vocal', 'chat', 'bridgebench', 'speed', 'best_available',
   'Tri, réponse directe et résumé à dire pendant un appel téléphonique : la latence prime, puis le français et la fiabilité.',
   '{"require_primary": true, "reasoning": "minimal", "max_latency_s": 3, "structured_output": true}',
   true, 'voice_router_service (decide_fast_route, synthesize_for_voice, synthesize_for_chat)'),
  ('stt', 'Transcription (parole vers texte)', 'audio', null, null, 'best_available',
   'Transcrire les messages vocaux du propriétaire (français) : fidélité, ponctuation, latence. Aucun classement collecté.',
   '{"language": "fr"}', true, 'Hermes stt + plugin gemini-stt'),
  ('embeddings', 'Vectorisation (embeddings)', 'embeddings', null, null, 'best_available',
   'Vecteurs de la mémoire Hindsight. Changer de modèle oblige à revectoriser toute la banque : jamais sans le propriétaire.',
   '{"revectorize_on_change": true}', true, 'Hindsight embeddings (banques walter, walter-shadow)'),
  ('rerank', 'Reclassement de résultats (rerank)', 'rerank', null, null, 'best_available',
   'Réordonner les souvenirs trouvés avant de les donner au modèle (rappel mémoire, voix). Aucun classement collecté.',
   '{"max_latency_s": 0.7}', true,
   'walter-memory search.rerank ; walter-voice-memory ; Hindsight reranker (drop-in 20-reranker-fallback.conf)')
on conflict (task) do update set label = excluded.label, interface = excluded.interface,
    quality_benchmark = excluded.quality_benchmark, quality_task = excluded.quality_task,
    default_objective = excluded.default_objective, description = excluded.description,
    requirements = excluded.requirements, internal = excluded.internal, consumers = excluded.consumers;

-- voice_assist: speed first, then French quality, then hallucination resistance (BridgeBench trustworthiness).
insert into models.task_benchmarks (task, benchmark, bench_task, is_primary, weight, note) values
  ('voice_assist', 'bridgebench', 'speed', true, 0.5, 'latence d''un appel vocal'),
  ('voice_assist', 'arena', 'text_french', false, 0.3, 'le propriétaire parle français'),
  ('voice_assist', 'bridgebench', 'trustworthiness', false, 0.2, 'ne rien inventer au téléphone')
on conflict do nothing;

-- Existing user-facing audio tasks are also used by modules (Hermes TTS, phone bridge).
update models.tasks set consumers = 'Hermes tts (messages vocaux Telegram)' where task = 'tts';
update models.tasks set consumers = 'Pont vocal téléphone /opt/openclaw/hermes_voice_bridge.py' where task = 'speech_to_speech';
update models.tasks set internal = true where interface = 'decisions';
update models.tasks set consumers = 'walter-memory triage + intention du routeur (llm.decide / intent.chain)' where task = 'decision';

insert into models.schema_migrations (version) values ('020_internal_postes') on conflict do nothing;
commit;

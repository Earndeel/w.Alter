-- 2026-10-22 (owner): a task to watch a video and analyse it (a client's reference video, the review of a generated
-- film) — until now only images were analysed. No arena measures it (Artificial Analysis and Arena rank video
-- generation only); Video-MME is saturated (~90 %). Boards: Video-MME-v2 (measured by its authors, rarely updated)
-- and LLM Stats video boards (current, but every score self-reported by the vendor: weighed half in scoring).
-- modes = {video}: only offers that declare video input count, so a model that cannot read a video is never chosen.
begin;
insert into models.tasks (task, label, interface, quality_benchmark, quality_task, default_objective, description,
                          modes, intent_hint, requirements, internal) values
  ('video_understanding', 'Analyse vidéo', 'chat', 'video_mme_v2', 'with_subtitles', 'best_available',
   'Regarder une vidéo fournie et l''analyser : plans, mouvements, rythme, montage, texte et son. Seuls les modèles '
   'qui acceptent une vidéo en entrée sont candidats. Classé sur Video-MME-v2 (mesuré par ses auteurs) et les '
   'tableaux vidéo de LLM Stats (scores déclarés par les éditeurs, comptés moitié).',
   '{video}',
   'Analyser une vidéo fournie (fichier ou lien) : ce qui s''y passe, les plans, le rythme, le montage, le texte ou le son ; comparer ou critiquer une vidéo existante (pas en générer une)',
   '{}', false)
on conflict (task) do update set label = excluded.label, interface = excluded.interface,
    quality_benchmark = excluded.quality_benchmark, quality_task = excluded.quality_task,
    default_objective = excluded.default_objective, description = excluded.description, modes = excluded.modes,
    intent_hint = excluded.intent_hint, requirements = excluded.requirements, internal = excluded.internal;

insert into models.task_benchmarks (task, benchmark, bench_task, is_primary, weight, note) values
  ('video_understanding', 'video_mme_v2', 'with_subtitles', true, 0.30, 'Video-MME-v2 avec sous-titres : score par groupes de questions, mesuré par ses auteurs'),
  ('video_understanding', 'video_mme_v2', 'without_subtitles', false, 0.10, 'Video-MME-v2 sans sous-titres : l''image seule'),
  ('video_understanding', 'llm_stats', 'lvbench', false, 0.15, 'LVBench : vidéos longues (jusqu''à 2 h), score déclaré par l''éditeur'),
  ('video_understanding', 'llm_stats', 'videommmu', false, 0.15, 'VideoMMMU : connaissances tirées de vidéos de cours, score déclaré'),
  ('video_understanding', 'llm_stats', 'video-mme', false, 0.10, 'Video-MME (v1, saturé), score déclaré'),
  ('video_understanding', 'llm_stats', 'mlvu', false, 0.05, 'MLVU : vidéos longues multi-tâches, score déclaré'),
  ('video_understanding', 'llm_stats', 'longvideobench', false, 0.05, 'LongVideoBench, score déclaré'),
  ('video_understanding', 'llm_stats', 'mvbench', false, 0.05, 'MVBench : compréhension temporelle sur clips courts, score déclaré'),
  ('video_understanding', 'arena', 'vision', false, 0.05, 'Arena Vision : lecture des images (votes humains)')
on conflict (task, benchmark, bench_task) do update set is_primary = excluded.is_primary, weight = excluded.weight,
    note = excluded.note;

comment on column models.offers.modes is
  'What the offer does or reads besides text: media generation modes (t2v, i2v, r2v, v2v, t2i, i2i); for chat and '
  'decision offers the inputs the model accepts (image, audio, video, file — from OpenRouter''s input_modalities).';
insert into models.schema_migrations (version) values ('031_video_understanding') on conflict do nothing;
commit;

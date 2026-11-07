-- Router tasks ("postes"). default_objective follows the owner's routing philosophy:
--   general text work climbs the AA Pareto ladder (value: L1 anchor, L2 knee, L3 ceiling);
--   a design domain escalates to that domain's Design Arena leader (best_available);
--   media defaults to value until the owner states a preference (image: best_available, declared 2026-10-02).
begin;
insert into models.tasks (task, label, interface, quality_benchmark, quality_task, default_objective, description) values
  ('general',          'Texte général (niveaux L1/L2/L3)', 'chat',  'aa_intelligence', 'intelligence', 'value',          'Résumé, actualité, analyse, comparatif, rédaction'),
  ('frontend',         'Site web / landing',               'chat',  'da_models', 'website',       'best_available', 'Design Arena Website'),
  ('ui_component',     'Composant d''interface',           'chat',  'da_models', 'uicomponent',   'best_available', 'Design Arena UI Component'),
  ('3d',               '3D / WebGL',                       'chat',  'da_models', '3d',            'best_available', 'Design Arena 3D'),
  ('gamedev',          'Jeu (canvas / HTML5)',             'chat',  'da_models', 'gamedev',       'best_available', 'Design Arena Game Dev'),
  ('dataviz',          'Visualisation de données',         'chat',  'da_models', 'dataviz',       'best_available', 'Design Arena Data Viz'),
  ('svg',              'SVG / vectoriel',                  'chat',  'da_models', 'svg',           'best_available', 'Design Arena SVG'),
  ('fullstack',        'Application full-stack (agent)',   'chat',  'da_agents', 'fullstack',     'best_available', 'Design Arena agents Full-Stack'),
  ('mobile_app',       'Application mobile (agent)',       'chat',  'da_agents', 'mobileapps',    'best_available', 'Design Arena agents Mobile Apps'),
  ('logo',             'Logo / identité visuelle',         'image', 'da_models', 'logo',          'best_available', 'Design Arena Logo'),
  ('graphic_design',   'Graphisme / affiche',              'image', 'da_models', 'graphicdesign', 'best_available', 'Design Arena Graphic Design'),
  ('text_to_image',    'Image',                            'image', 'aa_mm', 'text_to_image',     'value',          'AA Text-to-Image Arena'),
  ('text_to_video',    'Vidéo depuis texte',               'video', 'aa_mm', 'text_to_video',     'value',          'AA Text-to-Video Arena'),
  ('image_to_video',   'Animer une image',                 'video', 'aa_mm', 'image_to_video',    'value',          'AA Image-to-Video Arena'),
  ('tts',              'Voix (lecture)',                   'audio', 'aa_mm', 'tts',               'value',          'AA Provider Voice Elo'),
  ('speech_to_speech', 'Conversation vocale temps réel',   'audio', 'aa_mm', 'speech_to_speech',  'value',          'AA Speech to Speech Index'),
  ('music',            'Musique',                          'music', null, null,                   'value',          'Aucun classement collecté : choix sur offres uniquement'),
  ('weather',          'Météo',                            'tool',  null, null,                   'tool',           'Outil météo, pas de LLM'),
  ('calculation',      'Calcul',                           'tool',  null, null,                   'tool',           'Calcul déterministe'),
  ('research',         'Recherche web',                    'tool',  null, null,                   'tool',           'Recherche web + synthèse par le niveau général')
on conflict (task) do update set label = excluded.label, interface = excluded.interface,
  quality_benchmark = excluded.quality_benchmark, quality_task = excluded.quality_task,
  default_objective = excluded.default_objective, description = excluded.description;

-- Until 2026-10-29 this migration also inserted the first instance's declared preference for images. Preferences are
-- an instance's data (models.preferences), never a software default: a new database starts with none (Walter Clean).

insert into models.schema_migrations (version) values ('002_tasks') on conflict do nothing;
commit;

-- 2026-11-19 (owner: lot P1 des projections d'état courant, « latence < 50 ms »): the project projection reads the
-- current g1 knowledge of a subject by its normalised key (knowledge.subject_key: « project:W.Alter » =
-- « project:walter »), and the catalog of projects by their raw labels. Two partial expression indexes; a read path
-- only, no new storage. Built concurrently (migrations run in autocommit), idempotent.
create index concurrently if not exists derived_g1_subject_key on core.derived_items
    ((regexp_replace(lower(attributes->>'subject'), '[^a-z0-9:]', '', 'g')))
    where derived_by = 'l3.extract' and generation = 'g1' and kind <> 'summary';
create index concurrently if not exists derived_g1_project_label on core.derived_items ((attributes->>'subject'))
    where derived_by = 'l3.extract' and generation = 'g1' and kind <> 'summary'
      and (attributes->>'subject') ilike 'project:%';

-- 2026-10-29 (Walter Clean): the embeddings poste's change rule named the first instance's owner and the Hindsight
-- banks retired on 2026-10-19. Neutral rule; the selection itself is unchanged.
BEGIN;
update models.tasks
   set requirements = jsonb_set(requirements, '{on_change}',
       to_jsonb('Changer de modèle d''embeddings = revectoriser tout l''index de la mémoire : opération lourde, à planifier avec le propriétaire de l''instance ; l''ancien modèle reste en place tant que ce n''est pas fait.'::text))
 where task = 'embeddings' and requirements ? 'on_change';
insert into models.schema_migrations (version) values ('038_neutral_embeddings_requirement') on conflict do nothing;
COMMIT;

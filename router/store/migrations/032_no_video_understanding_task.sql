-- 2026-10-22 (owner): « on n'a pas de benchmark satisfaisant sur la vidéo, donc pas besoin d'en faire une catégorie
-- spécifique ». Task video_understanding (031) and its boards withdrawn the same day; what stays is the knowledge of
-- which models read a video (chat offers' `modes`) and the hard constraint `require = video_input` on any task.
begin;
delete from models.preferences where task = 'video_understanding';
delete from models.alerts where task = 'video_understanding';
delete from models.selection where task = 'video_understanding';
delete from models.dossiers where task = 'video_understanding';
delete from models.tasks where task = 'video_understanding';   -- task_benchmarks follow (on delete cascade)
delete from models.snapshots where kind = 'video_evals';        -- the boards' raw pages, read once that day
insert into models.schema_migrations (version) values ('032_no_video_understanding_task') on conflict do nothing;
commit;

-- A newer version of the best measured model can lead a media task before its board ranks it (select._executable_first,
-- 2026-10-14): it has no score of its own. Its predecessor's score stays in reasons.measured_quality.
alter table models.selection alter column quality drop not null;
comment on column models.selection.quality is 'Score on the task quality unit; null = newer version not yet ranked on this board (predecessor score in reasons.measured_quality)';

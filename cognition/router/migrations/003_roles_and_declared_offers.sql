-- Monsieur keeps several favourites per task, one per use ("rôle"): video has a premium pick, a cheap
-- action-scene pick, a best-ratio pick and a budget pick. Each favourite has its own watch rule:
--   quality   : alert when any model scores higher on the task leaderboard (premium / default favourites)
--   dominance : alert only when a model scores higher AND costs no more per unit (ratio / budget picks)
--   none      : never alert (no comparable measurement)
-- Offers can also be declared by Monsieur (e.g. Google Flow web UI): access 'ui' = usable by hand or through
-- the browser, not through an API.
begin;
alter table models.preferences add column if not exists role text not null default 'default';
alter table models.preferences add column if not exists watch text not null default 'quality';
alter table models.preferences drop constraint if exists preferences_watch_check;
alter table models.preferences add constraint preferences_watch_check check (watch in ('quality', 'dominance', 'none'));
alter table models.preferences drop constraint if exists preferences_pkey;
alter table models.preferences add primary key (task, role);

alter table models.alerts add column if not exists role text not null default '';
alter table models.alerts drop constraint if exists alerts_kind_task_subject_key;
alter table models.alerts add constraint alerts_kind_task_role_subject_key unique (kind, task, role, subject);

alter table models.offers drop constraint if exists offers_access_check;
alter table models.offers add constraint offers_access_check check (access in ('paid', 'subscription', 'free', 'ui'));

insert into models.schema_migrations (version) values ('003_roles_and_declared_offers') on conflict do nothing;
commit;

-- 2026-11-16 (owner): a padlock per active model on the library page. Locked (default, the behaviour so far): the model
-- stays until the owner accepts a proposal on Telegram. Unlocked: the router adopts by itself the model that overtakes
-- it in its category (same path as the « Passer à … » button) and only informs the owner afterwards.
begin;
alter table models.preferences add column if not exists locked boolean not null default true;
comment on column models.preferences.locked is
    'true (default): the pinned model changes only on the owner''s Telegram answer; false: alerts.auto_adopt switches it '
    'to the model overtaking it (challenger / tier / new #1) and the owner is informed (padlock of the library page)';
insert into models.schema_migrations (version) values ('042_preferences_locked') on conflict do nothing;
commit;

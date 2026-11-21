-- A1 (2026-11-19, owner: « Réutilise le fil déjà choisi par le préflight lorsqu'il est suffisamment fiable … En cas
-- d'incertitude, conserve l'échange non rattaché »). Additive and idempotent.
begin;

-- The preflight's thread decision as Walter Decision gave it (the run's thread_id alone lost its confidence).
alter table runs.runs add column if not exists thread_choice jsonb;
comment on column runs.runs.thread_choice is 'The preflight''s thread decision for this turn: {confidence (0..1), new (bool), degraded (bool)}; thread_id holds the chosen thread. Read by Memory views to attach the exchange without a second decision.';

-- An exchange can be recorded as not attached (uncertain): it is never retried, never a made-up subject.
alter table views.member alter column view_key drop not null;
alter table views.member add column if not exists thread_id text;
create index if not exists member_thread_idx on views.member (thread_id) where thread_id is not null;
comment on column views.member.view_key is 'The subject; null = recorded as not attached (attached_by = unattached: the thread decision was not sure enough).';
comment on column views.member.thread_id is 'The Context/Run-plane thread the exchange was attached through (subject:… or task:…): later exchanges of a task thread join the same subject.';
comment on column views.member.attached_by is 'rule (short reply) | preflight (the turn''s thread decision) | preflight_session (unsure pick = the session''s subject) | preflight_new | decision (Walter Decision, no preflight) | new | unattached; before 2026-11-19 also decision/new from the views'' own question';

commit;

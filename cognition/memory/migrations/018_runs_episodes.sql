-- Walter Run Plane, P4 (2026-10-28): episodes of significant runs, their evaluation, and corrections linked to the
-- run they correct. Additive. An episode summarises a run and points back to its tasks, sessions and observations;
-- it never replaces them. A correction is a new run whose parent_run_id is the corrected run; the corrected run's
-- episode gets a new version, the previous versions stay.
alter table runs.runs add column if not exists act text;
alter table runs.runs add column if not exists correction jsonb;
comment on column runs.runs.act is 'What the request does to its thread, from the walter-context preflight: new | continue | approve | correct | inform.';
comment on column runs.runs.correction is 'For a run that corrects its parent: {scope: run | category:<x> | durable, note}. Default scope run; durable only when the owner says so.';

create table if not exists runs.episodes (
    run_id      uuid not null references runs.runs (run_id),
    version     int not null,
    summary     text,
    evaluation  jsonb not null,
    facts       jsonb not null default '{}'::jsonb,
    model       text,
    reason      text not null default 'run_ended',
    created_at  timestamptz not null default now(),
    primary key (run_id, version)
);
comment on table runs.episodes is 'Episode of a significant run (delegation, tools, observations), versioned: a correction of the run adds a version.';
comment on column runs.episodes.summary is 'Short factual summary written by the Router''s summarization poste from the run''s records only; null when the run is local_only or the model is unavailable.';
comment on column runs.episodes.evaluation is '{technical: {status, tasks, tasks_failed, model_calls, model_failures}, functional: {contract, observations}, satisfaction: unknown | corrected | confirmed | refused, cost_usd, seconds}. Satisfaction is never inferred from silence.';
comment on column runs.episodes.facts is 'Deterministic material the summary was written from: goal, tasks, sellers/subjects observed, children and parent runs.';
comment on column runs.episodes.reason is 'run_ended | child_run (a correction or continuation arrived) | manual.';

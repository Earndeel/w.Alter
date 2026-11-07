-- 2026-10-26 (owner): « cela doit être fait automatiquement à partir de maintenant, fais un guardian dans le module
-- qui s'occupe de la maintenance de celui-ci ». One row per incident the guardian saw (a source too old, a provider
-- down, a failing test, a failed cycle) and what it did about it.
begin;
create table if not exists models.guardian_incidents (
    incident_id     bigserial primary key,
    key             text not null,
    kind            text not null,
    subject         text not null,
    status          text not null default 'open',
    opened_at       timestamptz not null default now(),
    last_seen_at    timestamptz not null default now(),
    closed_at       timestamptz,
    attempts        integer not null default 0,
    last_attempt_at timestamptz,
    detail          jsonb not null default '{}'::jsonb,
    verdict         jsonb,
    notified_at     timestamptz
);
create unique index if not exists guardian_incidents_one_open on models.guardian_incidents (key) where closed_at is null;

comment on table models.guardian_incidents is
    'Maintenance incidents of the Walter Router seen by its guardian (guardian/): detection, repair attempts, outcome.';
comment on column models.guardian_incidents.incident_id is 'Incident number.';
comment on column models.guardian_incidents.key is
    'Stable identity of the problem (source:aa_stt, provider:kie, test:<pytest node id>, cycle): one open row per key.';
comment on column models.guardian_incidents.kind is
    'source_stale | source_error | provider_down | test_failure | cycle_failed.';
comment on column models.guardian_incidents.subject is 'What is affected: source kind, provider, test node id or run.';
comment on column models.guardian_incidents.status is
    'open (seen, not handled yet) | repairing | fixed (patch applied and verified) | external (cause outside the module: '
    'provider or site outage, waiting) | needs_owner (a decision only the owner can take) | deferred (verified patch '
    'waiting for files another session is editing) | resolved (gone by itself).';
comment on column models.guardian_incidents.opened_at is 'First detection.';
comment on column models.guardian_incidents.last_seen_at is 'Last check that still saw the problem.';
comment on column models.guardian_incidents.closed_at is 'When it was fixed or went away; null while open.';
comment on column models.guardian_incidents.attempts is 'Repair agent runs spent on this incident.';
comment on column models.guardian_incidents.last_attempt_at is 'Last repair agent run.';
comment on column models.guardian_incidents.detail is 'Evidence of the detection (age, error, probe answer, test output).';
comment on column models.guardian_incidents.verdict is
    'Last repair verdict: agent outcome, cause, changed files, gate results, commit, deferred patch.';
comment on column models.guardian_incidents.notified_at is 'When the owner was told (once per incident outcome).';

insert into models.schema_migrations (version) values ('033_guardian') on conflict do nothing;
commit;

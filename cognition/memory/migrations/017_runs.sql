-- Walter Run Plane (P0, 2026-10-27, Monsieur: run_id = Walter's canonical identifier across harnesses, tools,
-- sub-agents and Memory; DECISIONS.md 2026-10-27). Additive: nothing existing is rewritten.
-- Thread = long-lived subject (views); session = a harness's execution context (walter_logs.sessions);
-- run = the handling of one request, from the message to the answer; task = a sub-task delegated inside a run.
-- Written only through walter_memory.runs (the hook adapters, walter-router's sub-agent); the bus carries the same
-- events (run.created, run.ended, task.started, task.ended, routing.selected) for other consumers.
create schema if not exists runs;
comment on schema runs is 'Walter Run Plane: runs, their tasks and links (sessions, model calls, observations, episodes). Written by walter_memory.runs only.';

create table if not exists runs.runs (
    run_id         uuid primary key,
    parent_run_id  uuid references runs.runs (run_id),
    thread_id      text,
    origin         jsonb not null,
    goal           text,
    status         text not null default 'open' check (status in ('open', 'ended', 'failed', 'cancelled', 'abandoned')),
    level          text,
    routing        jsonb,
    budgets        jsonb,
    costs          jsonb,
    privacy_class  text not null default 'cloud_allowed',
    dedupe_key     text unique,
    started_at     timestamptz not null,
    ended_at       timestamptz,
    updated_at     timestamptz not null default now()
);
comment on table runs.runs is 'One row per run: the handling of one request (owner message, cron, guardian), whatever the runtime.';
comment on column runs.runs.run_id is 'Canonical run identifier (uuid7), propagated as WALTER_RUN_ID / run_id to tools, sub-agents and Memory.';
comment on column runs.runs.parent_run_id is 'The run this one continues or corrects (a correction is a new run, the parent stays untouched).';
comment on column runs.runs.thread_id is 'Long-lived subject (views.view key subject:…) once known; may be filled after the run starts.';
comment on column runs.runs.origin is '{channel, runtime, session_id, turn}: where the request came from and which harness session ran it.';
comment on column runs.runs.goal is 'The request, masked and truncated; null when the run is local_only.';
comment on column runs.runs.status is 'open while running; ended / failed / cancelled when closed; abandoned when no end arrived within 24 h.';
comment on column runs.runs.level is 'Effort level L0-L4 from the walter-context preflight, when known.';
comment on column runs.runs.routing is 'Model decision for the run''s main agent: {task, level, model, provider, applied, constraint}; applied=false with constraint=harness_imposed when the harness keeps its own model.';
comment on column runs.runs.budgets is 'Budgets granted to the run (seconds, turns, usd), when the control plane sets them.';
comment on column runs.runs.costs is 'Measured costs (usd, tokens, seconds), filled at the end.';
comment on column runs.runs.privacy_class is 'Same classes as core.events; only tightened.';
comment on column runs.runs.dedupe_key is 'Adapter key (runtime/session/turn) making run creation idempotent.';

create table if not exists runs.tasks (
    task_id         uuid primary key,
    run_id          uuid not null references runs.runs (run_id),
    parent_task_id  uuid references runs.tasks (task_id),
    kind            text not null,
    goal            text,
    spec            jsonb,
    status          text not null default 'open' check (status in ('open', 'ended', 'failed', 'cancelled', 'abandoned')),
    session_id      text,
    routing         jsonb,
    result          jsonb,
    started_at      timestamptz not null,
    ended_at        timestamptz
);
comment on table runs.tasks is 'Sub-tasks delegated inside a run (walter_run sub-agent, Hermes delegate_task, Claude Code Agent, Codex spawn, DSH subagent).';
comment on column runs.tasks.kind is 'walter_run | hermes_delegate | cc_agent | codex_spawn | dsh_subagent';
comment on column runs.tasks.spec is 'TaskSpec v1 as received (toolsets, constraints, output schema, budget); never a secret.';
comment on column runs.tasks.session_id is 'walter_logs session holding the task''s full trace.';
comment on column runs.tasks.result is 'Compact outcome {ok, error, model, turns, seconds}; the full trace stays in walter_logs.';
create index if not exists tasks_run on runs.tasks (run_id);

create table if not exists runs.links (
    run_id  uuid not null references runs.runs (run_id),
    kind    text not null,
    ref     text not null,
    at      timestamptz not null default now(),
    primary key (run_id, kind, ref)
);
comment on table runs.links is 'What a run touched or produced: session, exec (models.exec_log), observation, skill, recipe, episode.';

create index if not exists runs_open on runs.runs (status, started_at) where status = 'open';
create index if not exists runs_thread on runs.runs (thread_id);
create index if not exists runs_started on runs.runs (started_at desc);

alter table system.agent_calls add column if not exists run_id uuid;
comment on column system.agent_calls.run_id is 'Run this model call belongs to (runs.runs), when known.';

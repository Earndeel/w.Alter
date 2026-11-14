-- Socle M2 (2026-11-11, SOCLE.md § 3 A3 + A4). Additive and idempotent: nothing existing is rewritten.
-- A3: the owner's durable task (kind 'objective') is a row of runs.tasks — the Run Plane carries it, there is no other
--     task manager. It follows the thread, not the session: another session or interface finds it again.
-- A4: a run's structured outcome (runs.runs.outcome) and its episode's outcome (runs.episodes.outcome) make execution
--     experience a memory (published as a g1 derived item kind 'experience' by walter_memory.episodes).
begin;

alter table runs.tasks add column if not exists thread_id text;
alter table runs.tasks add column if not exists progress jsonb;
alter table runs.tasks add column if not exists last_outcome jsonb;
alter table runs.tasks add column if not exists updated_at timestamptz;
alter table runs.tasks drop constraint if exists tasks_status_check;
alter table runs.tasks add constraint tasks_status_check check (status in
    ('open', 'ended', 'failed', 'cancelled', 'abandoned', 'suspended', 'done'));
comment on column runs.tasks.kind is 'objective (the owner''s task, A3: goal, thread, open | suspended | done | failed | cancelled) | walter_run | hermes_delegate | cc_agent | codex_spawn | dsh_subagent (sub-tasks delegated inside a run: open | ended | failed | cancelled | abandoned)';
comment on column runs.tasks.status is 'objective: open | suspended (no activity, swept, never lost) | done | failed | cancelled; delegated sub-task: open | ended | failed | cancelled | abandoned (no end within 24 h)';
comment on column runs.tasks.parent_task_id is 'For a delegated sub-task started inside a run that belongs to an objective: that objective.';
comment on column runs.tasks.run_id is 'The run that opened the task (objective: its origin run; every attempt is in runs.task_runs).';
comment on column runs.tasks.result is 'Delegated sub-task: compact outcome {ok, error, model, turns, seconds}. Objective: {summary, refs: {runs, objects, files}} once known.';
comment on column runs.tasks.thread_id is 'Objective: the thread (preflight subject, e.g. subject:…) it belongs to; continuations of the thread attach to it from any session or interface.';
comment on column runs.tasks.progress is 'Objective: {done: [str], next: [str], pending: [str], notes: [{at, note}]} — steps done and still to do, from the run episodes and the engine''s task_state tool.';
comment on column runs.tasks.last_outcome is 'Objective: {status, reason, run_id, at} of its latest evaluated attempt (episode outcome).';
comment on column runs.tasks.updated_at is 'Last change of the task (opening, attempt attached, progress, status); the suspension sweep reads it.';
create index if not exists tasks_objective_thread on runs.tasks (thread_id, updated_at desc) where kind = 'objective';
create index if not exists tasks_objective_open on runs.tasks (status, updated_at) where kind = 'objective';
create index if not exists tasks_parent on runs.tasks (parent_task_id) where parent_task_id is not null;

create table if not exists runs.task_runs (
    task_id  uuid not null references runs.tasks (task_id) on delete cascade,
    run_id   uuid not null references runs.runs (run_id) on delete cascade,
    role     text not null check (role in ('origin', 'attempt')),
    at       timestamptz not null default now(),
    primary key (task_id, run_id)
);
comment on table runs.task_runs is 'Runs that worked on an objective (A3): origin = the run that opened it, attempt = a later run of the thread (continue, correct, approve) or a delegated run inheriting through parent_run_id.';
comment on column runs.task_runs.task_id is 'The objective (runs.tasks kind objective).';
comment on column runs.task_runs.run_id is 'A run that worked on it.';
comment on column runs.task_runs.role is 'origin (opened the objective) | attempt (a later run attached to it).';
comment on column runs.task_runs.at is 'When the run was attached.';
create index if not exists task_runs_run on runs.task_runs (run_id);

alter table runs.runs add column if not exists outcome jsonb;
comment on column runs.runs.outcome is 'Structured end of the run given by the runtime (A4): {status: ok | failed | cancelled | interrupted, error: {kind, message (masked, bounded)}, steps, tool_calls, tool_errors}.';

alter table runs.episodes add column if not exists outcome jsonb;
comment on column runs.episodes.outcome is 'What the run achieved (A4): {status: achieved | partial | failed | blocked | unknown, errors: [{what, why}], lessons: [str], solutions: [str], pending: [str]}; deterministic part from the traces (failed tools, run outcome, model failures), lists completed by the summarization poste strictly from the same material; published as core.derived_items kind experience.';
comment on column runs.episodes.evaluation is '{technical: {status, tasks, tasks_failed, model_calls, model_failures, tools: {calls, errors, failing}}, functional: {contract, observations}, satisfaction: unknown | corrected | confirmed | refused, cost_usd, seconds}. Satisfaction is never inferred from silence.';

commit;

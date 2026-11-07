-- walter-logs (2026-10-04): the raw session log of every agent that works for Monsieur, whatever the runtime
-- (Hermes and its profiles, Claude Code, Codex, DeepSeek Harness, later Walter's own runtime). Everything the agents
-- did, in order: messages, reasoning, tool calls with their arguments, tool results in full, model selections.
-- Vocabulary = DeepSeek Harness session log (user/message, assistant/message, assistant/reasoning, tool/call,
-- tool/result, model/selection, compaction/summary, system/message...), so a future runtime can use these tables as
-- its persistence backend. Append-only. Secrets are masked before storage; privacy class per event (same policies as
-- core.events). core.events stays the journal of Monsieur's life; walter_logs is the journal of what the agents did.
begin;
create schema if not exists walter_logs;
comment on schema walter_logs is 'walter-logs: raw, append-only session log of every agent runtime (DSH vocabulary). Secrets masked at write.';

create table if not exists walter_logs.sessions (
    session_id        text primary key,               -- '<runtime>/<profile or account>/<native id>'
    runtime           text not null,                  -- hermes, claude_code, codex, dsh, ...
    native_id         text not null,
    profile           text,                           -- Hermes profile, Codex originator...
    platform          text,                           -- telegram, cli, desktop, cron, codex_exec...
    title             text,
    model             text,
    cwd               text,
    parent_session_id text,
    started_at        timestamptz,
    ended_at          timestamptz,
    last_event_at     timestamptz,
    privacy_class     text not null default 'cloud_allowed',
    last_seq          bigint not null default 0,
    turns             int not null default 0,
    meta              jsonb not null default '{}'::jsonb,
    updated_at        timestamptz not null default now()
);
create index if not exists sessions_runtime_time on walter_logs.sessions (runtime, started_at desc);
create index if not exists sessions_last on walter_logs.sessions (last_event_at desc);

create table if not exists walter_logs.events (
    session_id    text not null references walter_logs.sessions on delete cascade,
    seq           bigint not null,                    -- order inside the session (gaps allowed)
    type          text not null,                      -- DSH event type
    occurred_at   timestamptz not null,
    turn          int,                                -- n-th human request of the session
    call_id       text,                               -- links tool/call ↔ tool/result
    tool          text,
    model         text,
    status        text,                               -- tool/result: ok | error
    text          text,                               -- the content, secrets masked (full, never truncated)
    data          jsonb not null default '{}'::jsonb, -- everything else (usage, flags, ids)
    chars         int not null default 0,
    privacy_class text not null,
    source_ref    text not null,                      -- idempotency key inside the source (row id / byte offset)
    ingested_at   timestamptz not null default now(),
    tsv           tsvector generated always as (
                      setweight(to_tsvector('simple', search.f_unaccent(coalesce(tool, ''))), 'A') ||
                      to_tsvector('simple', search.f_unaccent(left(coalesce(text, ''), 100000)))) stored,
    primary key (session_id, seq),
    unique (session_id, source_ref)
);
create index if not exists events_tsv on walter_logs.events using gin (tsv);
create index if not exists events_time on walter_logs.events (occurred_at desc);
create index if not exists events_type_time on walter_logs.events (type, occurred_at desc);
create index if not exists events_tool on walter_logs.events (tool, occurred_at desc) where tool is not null;
create index if not exists events_call on walter_logs.events (call_id) where call_id is not null;

insert into ingestion.connectors (connector, source, mode, description, freshness_target)
select 'walter_logs', 'hermes', 'push',
       'walter-logs: Hermes (all profiles), Claude Code, Codex, DSH session logs → walter_logs.*, triggered by file changes (walter-logs-watch); no timer',
       null
where exists (select 1 from core.sources where source = 'hermes')
on conflict (connector) do nothing;
commit;

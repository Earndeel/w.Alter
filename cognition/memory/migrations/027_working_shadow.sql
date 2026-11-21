-- Working memory in shadow (2026-11-02, Memory V1 P1.1): after each new conversation message, the working state the
-- adaptive policy would give Context, and whether it would call a model now. Recorded only: nothing is injected and
-- extraction keeps its 20-minute policy while organic.toml [working_memory] mode = "shadow".
begin;
create table if not exists extraction.working_shadow (
    id             bigserial primary key,
    at             timestamptz not null default now(),
    source         text not null,
    thread_id      text not null,
    last_event_at  timestamptz,
    pending        integer not null,
    interpreted    integer not null,
    plan_items     integer not null default 0,
    tokens         integer not null,
    build_ms       integer not null,
    would_call     boolean not null,
    reason         text,
    live_due       boolean not null,
    privacy_class  text not null check (privacy_class in ('local_only', 'redacted_cloud', 'cloud_allowed')),
    state          jsonb not null
);
create index if not exists working_shadow_thread on extraction.working_shadow (source, thread_id, at desc);
create index if not exists working_shadow_at on extraction.working_shadow (at);
comment on table extraction.working_shadow is 'P1.1 shadow: working state (SessionState fields, verbatim pending owner messages) per new message, adaptive decision (would_call, reason) vs the live 20-minute policy (live_due); privacy_class = strictest of its content; pruned after 30 days';
commit;

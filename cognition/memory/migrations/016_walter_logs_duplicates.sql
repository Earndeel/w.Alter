-- walter-logs duplicates quarantine (2026-10-25, Monsieur's choice; DECISIONS.md 2026-10-25).
-- Later copies of an event (same event_key in the session, see 015) written by the runtimes themselves before the
-- ingestion was idempotent on identity: moved here out of the journal, with the seq of the copy that stays.
-- Reversible: insert back into walter_logs.events from this table. Filled by `connectors/walter_logs.py dedup --apply`.
create table if not exists walter_logs.duplicates (
    session_id    text not null,
    seq           bigint not null,                    -- seq the copy had in walter_logs.events
    duplicate_of  bigint not null,                    -- seq of the first copy, still in walter_logs.events
    event_key     text not null,
    type          text not null,
    occurred_at   timestamptz not null,
    turn          int,
    call_id       text,
    tool          text,
    model         text,
    status        text,
    text          text,
    data          jsonb not null default '{}'::jsonb,
    chars         int not null default 0,
    privacy_class text not null,
    source_ref    text not null,
    ingested_at   timestamptz not null,
    quarantined_at timestamptz not null default now(),
    primary key (session_id, seq)
);
comment on table walter_logs.duplicates is
  'Quarantined later copies of walter_logs events (same event_key in the session). Reversible; not read by agents.';

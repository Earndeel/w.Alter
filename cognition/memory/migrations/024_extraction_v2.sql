-- Incremental knowledge extraction for every runtime (2026-11-02, Memory V1 P0).
--
-- The L3 extractor v1 marked a whole Hermes session as done after its first summary and re-read local_only sessions
-- forever. v2 (walter_memory/extract2.py) tracks coverage per canonical event: a thread (one conversation of any
-- runtime) gets new segments as it grows; each segment records what was extracted, rejected (invalid provenance) or
-- not processed and why (local_only, filtered noise). Derived knowledge can now be superseded (corrections).
begin;
create schema if not exists extraction;
comment on schema extraction is 'Walter Memory: progress of the derived-knowledge processors (threads to process, segments, event coverage)';

create table if not exists extraction.state (
    key        text primary key,
    value      jsonb not null,
    updated_at timestamptz not null default now()
);
comment on table extraction.state is 'processor settings that belong to this database (e.g. the V1 start: events ingested before it are pre-V1 history, never extracted automatically)';

create table if not exists extraction.threads (
    processor     text not null,
    source        text not null,
    thread_id     text not null,
    status        text not null default 'dirty' check (status in ('dirty', 'working', 'idle')),
    last_event_at timestamptz,
    dirty_since   timestamptz,
    claimed_at    timestamptz,
    attempts      integer not null default 0,
    retry_after   timestamptz,
    last_error    text,
    from_at       timestamptz,
    updated_at    timestamptz not null default now(),
    primary key (processor, source, thread_id)
);
create index if not exists threads_due on extraction.threads (processor, status, last_event_at);
comment on table extraction.threads is 'work list of a processor: a thread with uncovered events is dirty (set by the bus consumer and the reconciliation sweep); working = leased (claimed_at); from_at = explicit catch-up start for this thread (overrides the V1 start)';

create table if not exists extraction.segments (
    segment_id   uuid primary key default gen_random_uuid(),
    processor    text not null,
    version      text not null,
    source       text not null,
    thread_id    text not null,
    status       text not null check (status in ('extracted', 'empty', 'filtered', 'local_only_unavailable', 'failed')),
    event_ids    uuid[] not null,
    first_at     timestamptz,
    last_at      timestamptz,
    items        integer not null default 0,
    reused       integer not null default 0,
    superseded   integer not null default 0,
    rejected     jsonb not null default '[]',
    model        text,
    prompt_hash  text,
    cost_usd     numeric,
    usage        jsonb,
    latency_ms   integer,
    lag_s        integer,
    error        text,
    created_at   timestamptz not null default now()
);
create index if not exists segments_thread on extraction.segments (source, thread_id, created_at);
create index if not exists segments_created on extraction.segments (created_at);
comment on table extraction.segments is 'one processing of a set of events of a thread: extracted / empty (nothing durable) / filtered (noise, no model call) / local_only_unavailable (no authorised local model: never sent to a cloud model) / failed. rejected = items refused for invalid provenance (quarantine). lag_s = newest event ingested → knowledge written';

create table if not exists extraction.covered (
    processor  text not null,
    event_id   uuid not null,
    segment_id uuid not null references extraction.segments(segment_id),
    primary key (processor, event_id)
);
create index if not exists covered_segment on extraction.covered (segment_id);
comment on table extraction.covered is 'exact checkpoint: which canonical events a processor has handled (late or out-of-order events are simply not covered yet)';

alter table core.derived_items drop constraint if exists derived_items_status_check;
alter table core.derived_items add constraint derived_items_status_check
    check (status = any (array['legacy_derived', 'derived', 'verified', 'retracted', 'superseded']));
comment on column core.derived_items.status is 'derived/verified = current; superseded = replaced by a later item (attributes.superseded_by, valid_to); retracted; legacy_derived = pre-V1 history read as legacy';
commit;

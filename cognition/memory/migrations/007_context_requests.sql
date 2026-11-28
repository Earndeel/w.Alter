-- P6 / A8: every context assembly is logged (sizes per section, latency, mode) for the A/B comparison.
begin;
create table if not exists system.context_requests (
    request_id bigserial primary key,
    at         timestamptz not null default now(),
    caller     text not null,                 -- hermes-plugin | walter-core | voice | cli
    mode       text not null,                 -- shadow | on
    session_id text,
    query_sha  text not null,                 -- sha256 of the query (never the query itself)
    total_tokens int,
    sections   jsonb not null default '{}',
    latency_ms int
);
create index if not exists context_requests_at on system.context_requests (at desc);
commit;

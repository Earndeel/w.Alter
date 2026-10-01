-- Walter Memory P6 / A8 — per-call context metrics of the live agent (baseline and after the context engine).
begin;
create table if not exists system.agent_calls (
    response_id   text primary key,
    at            timestamptz not null,
    session_id    text,
    call_no       int,
    model         text,
    provider      text,
    input_tokens  int,            -- real context size sent
    cached_tokens int,            -- cache read
    uncached_tokens int generated always as (input_tokens - coalesce(cached_tokens, 0)) stored,
    output_tokens int,
    latency_s     real,
    context_engine text not null default 'baseline',   -- which context assembly produced this call (A/B)
    source_log    text
);
create index if not exists agent_calls_at on system.agent_calls (at desc);
create index if not exists agent_calls_session on system.agent_calls (session_id, call_no);
-- list prices used to estimate cost when billing is a subscription (USD per million tokens)
create table if not exists system.model_prices (
    model text primary key, input_per_m numeric, cached_input_per_m numeric, output_per_m numeric, updated_at date not null default current_date);
commit;

-- walter-context (P6 / P8.4): per-call trace of the context engine (zones, boundary, predicted cache) for the A/B.
begin;
alter table system.agent_calls add column if not exists context_trace jsonb;
commit;

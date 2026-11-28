-- Can Hermes actually run a model on this provider right now? A tiny live probe per provider (a few tokens)
-- at every refresh; the router skips providers whose last probe failed and falls back to the next route.
begin;
create table if not exists models.provider_status (
    provider   text primary key,             -- walter-router provider key (codex, openrouter, kie, arnict...)
    ok         boolean not null,
    checked_at timestamptz not null default now(),
    latency_ms int,
    detail     text
);
insert into models.schema_migrations (version) values ('008_provider_status') on conflict do nothing;
commit;

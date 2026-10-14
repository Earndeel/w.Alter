-- Monsieur's subscriptions: usage meter readings (declared plans live in config/subscriptions.json).
begin;

create table if not exists models.subscription_usage (
    reading_id   bigserial primary key,
    sub_id       text not null,                -- config/subscriptions.json id (openai-plus, anthropic-pro)
    read_at      timestamptz not null default now(),
    window_name  text not null,                -- session (5 h) | weekly | ...
    used_percent numeric(6, 2) not null,
    resets_at    timestamptz,
    source       text not null,                -- codex_usage_api | estimate_claude_code_logs | calibration
    estimated    boolean not null default false,
    detail       jsonb not null default '{}'::jsonb
);
create index if not exists subscription_usage_latest on models.subscription_usage (sub_id, window_name, read_at desc);

create or replace view models.latest_subscription_usage as
select distinct on (sub_id, window_name) *
from models.subscription_usage
order by sub_id, window_name, read_at desc;

insert into models.schema_migrations (version) values ('019_subscriptions') on conflict do nothing;
commit;

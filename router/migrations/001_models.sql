-- Walter Router — model catalogue the router picks from (schema `models` in hindsight-pg).
-- Truth = raw provider/leaderboard snapshots; everything else is derived and rebuilt on each refresh,
-- except the owner's preferences and alert verdicts, which are never overwritten by automation.
begin;
create schema if not exists models;

create table if not exists models.schema_migrations (
    version    text primary key,
    applied_at timestamptz not null default now()
);

-- One row per collected source document (AA intelligence, AA multimodal, Design Arena, OpenRouter, Kie, Codex).
create table if not exists models.snapshots (
    snapshot_id bigserial primary key,
    kind        text not null,
    fetched_at  timestamptz not null,
    source_url  text,
    sha256      text not null,
    row_count   int not null,
    raw         jsonb not null,
    unique (kind, sha256)
);
create index if not exists snapshots_kind_at on models.snapshots (kind, fetched_at desc);

-- Canonical model identities and the external keys that point to them.
create table if not exists models.canonical (
    model_id   text primary key,                  -- normalised family key, e.g. gpt-6-1-sol
    vendor     text,
    first_seen timestamptz not null default now()
);
create table if not exists models.aliases (
    namespace    text not null,                   -- aa | da | mm | openrouter | kie | codex
    external_key text not null,
    model_id     text not null references models.canonical,
    origin       text not null check (origin in ('auto', 'manual')),
    created_at   timestamptz not null default now(),
    primary key (namespace, external_key)
);

-- Measured quality, per benchmark/task, from the latest snapshot of each source.
create table if not exists models.benchmarks (
    snapshot_id  bigint not null references models.snapshots on delete cascade,
    benchmark    text not null,                   -- aa_intelligence | da_models | da_agents | aa_mm
    task         text not null,                   -- intelligence | website | 3d | text_to_image | ...
    external_key text not null,
    model_id     text references models.canonical,
    variant      text not null default '',        -- reasoning effort / quality tier (high, max, ...)
    display_name text,
    score        double precision not null,
    score_unit   text,
    cost         double precision,                -- benchmark cost as published (AA cost per task)
    cost_unit    text,
    released     text,
    extra        jsonb not null default '{}',
    primary key (snapshot_id, benchmark, task, external_key)
);
create index if not exists benchmarks_task on models.benchmarks (benchmark, task, score desc);

-- Callable offers: what a provider actually sells, at what price.
create table if not exists models.offers (
    snapshot_id   bigint not null references models.snapshots on delete cascade,
    provider      text not null,                  -- openrouter | kie | codex
    offer_key     text not null,                  -- provider's callable id (+ variant for Kie)
    model_id      text references models.canonical,
    interface     text not null,                  -- chat | image | video | music | audio
    access        text not null check (access in ('paid', 'subscription', 'free')),
    price_in_1m   double precision,               -- USD per 1M input tokens (chat)
    price_out_1m  double precision,               -- USD per 1M output tokens (chat)
    unit_price    double precision,               -- media: USD per unit
    unit          text,                           -- per image | per second | per request ...
    provider_created timestamptz,
    pricing       jsonb not null default '{}',    -- every published dimension, verbatim
    primary key (snapshot_id, provider, offer_key)
);
create index if not exists offers_model on models.offers (model_id);

-- Router tasks ("postes") and how their quality is measured.
create table if not exists models.tasks (
    task              text primary key,
    label             text not null,
    interface         text not null,              -- chat | image | video | audio | music | tool
    quality_benchmark text,                       -- null = no leaderboard yet (music) or tool task
    quality_task      text,
    default_objective text not null check (default_objective in ('value', 'best_available', 'tool')),
    description       text
);

-- The owner's preferences: always win over computed choices. Written only by an explicit declaration.
create table if not exists models.preferences (
    task             text primary key references models.tasks,
    objective        text check (objective in ('value', 'best_available')),
    pinned_model_id  text references models.canonical,
    pinned_variant   text not null default '',
    pinned_provider  text,
    note             text,
    declared_at      timestamptz not null default now()
);

-- Each refresh computes ranked candidates per task and level.
create table if not exists models.runs (
    run_id      bigserial primary key,
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    status      text not null default 'running' check (status in ('running', 'ok', 'failed')),
    summary     jsonb not null default '{}'
);
create table if not exists models.selection (
    run_id        bigint not null references models.runs on delete cascade,
    task          text not null references models.tasks,
    level         text not null,                  -- L1 | L2 | L3 | best
    rank          int not null,
    model_id      text not null references models.canonical,
    variant       text not null default '',
    display_name  text,
    quality       double precision not null,
    quality_unit  text,
    real_cost     double precision,               -- cheapest paid route, same unit as the benchmark cost
    cost_unit     text,
    provider      text,                           -- cheapest paid provider
    offer_key     text,
    subscription  text,                           -- subscription route available first (e.g. codex)
    reasons       jsonb not null default '{}',
    primary key (run_id, task, level, rank)
);

-- Notifications: challengers to a pinned model, unranked new releases, stale sources.
create table if not exists models.alerts (
    alert_id     bigserial primary key,
    kind         text not null check (kind in ('challenger', 'unranked', 'source_stale')),
    task         text not null default '',        -- '' for source-level alerts
    subject      text not null,                   -- challenger model_id/variant, offer key, or source kind
    evidence     jsonb not null default '{}',
    status       text not null default 'open'
                 check (status in ('baseline', 'open', 'notified', 'dismissed', 'adopted')),
    first_seen   timestamptz not null default now(),
    last_seen    timestamptz not null default now(),
    notified_at  timestamptz,
    verdict_note text,
    unique (kind, task, subject)
);

-- What the router reads: the latest successful run, preferences applied.
create or replace view models.latest_run as
    select run_id from models.runs where status = 'ok' order by run_id desc limit 1;

insert into models.schema_migrations (version) values ('001_models') on conflict do nothing;
commit;

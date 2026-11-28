-- Walter Memory P4 — entity resolution support + Kardex V1 relationship intelligence (L0, no LLM). 2026-10-01.
begin;
create table if not exists kardex.relationship_baselines (
    entity_id     uuid not null references core.entities(entity_id) on delete cascade,
    window_name   text not null check (window_name in ('7d','14d','30d','90d','365d','all')),
    channels      text[] not null default '{}',
    messages      int not null,
    from_me       int not null,
    from_them     int not null,
    msgs_per_day  real,
    active_days   int,
    initiation_ratio_me real,          -- share of conversation starts (after ≥6 h silence) made by Monsieur
    median_reply_me_s   real,          -- Monsieur's median reply latency (seconds)
    median_reply_them_s real,
    avg_len_me    real,
    avg_len_them  real,
    first_contact timestamptz,
    last_contact  timestamptz,
    computed_at   timestamptz not null default now(),
    processor_version text not null,
    primary key (entity_id, window_name)
);
create table if not exists kardex.communication_deviations (
    deviation_id  bigserial primary key,
    entity_id     uuid not null references core.entities(entity_id) on delete cascade,
    metric        text not null,
    baseline      real,
    current       real,
    ratio         real,
    baseline_window text not null,
    current_window  text not null,
    sample_size   int not null,
    observation   text not null,       -- what is measured, never a cause (§9/§10)
    confidence    text not null default 'low',
    detected_on   date not null default current_date,
    acknowledged_at timestamptz,
    processor_version text not null,
    unique (entity_id, metric, detected_on)
);
create index if not exists deviations_open on kardex.communication_deviations (detected_on desc) where acknowledged_at is null;
commit;

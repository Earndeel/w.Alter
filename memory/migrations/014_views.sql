-- Memory Views (walter-context v2, lot 3, step C, 2026-10-25): what Walter knows, organised for reading at the exact
-- depth a caller needs. Derived, versioned, sourced, with freshness. core.* is untouched; dropping this schema
-- loses nothing that cannot be rebuilt from core.events, core.derived_items and walter_logs.
--   view     one subject of knowledge (v0: subjects = threads of work across sessions and runtimes)
--   version  its renderings per depth (index | overview | synthesis | details), append-only, newest = current
--   member   the exchanges a subject view is made of (walter_logs positions): the `sources` depth
--   ledger   every attachment, re-attachment and rebuild, for audit and for the night pass
create schema if not exists views;
comment on schema views is 'Memory Views: derived knowledge by domain x horizon x depth, versioned and sourced (lot 3).';

create table if not exists views.view (
    view_key       text primary key,                       -- e.g. subject:3f9a2c1b
    domain         text not null check (domain in ('projects','profile','activities','relations','agenda',
                                                   'decisions','goals')),
    horizon        text not null check (horizon in ('instant','day','medium','long','stable')),
    title          text not null default '',
    status         text not null default 'active' check (status in ('active','dormant','merged','retired')),
    merged_into    text references views.view (view_key),
    privacy_class  text not null default 'cloud_allowed'
                   check (privacy_class in ('local_only','redacted_cloud','cloud_allowed')),
    first_at       timestamptz,
    last_at        timestamptz,
    embedding      vector(256),                            -- index + overview, local potion model: the shortlist
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);
create index if not exists view_domain_last on views.view (domain, last_at desc) where status = 'active';

create table if not exists views.version (
    view_key       text not null references views.view (view_key) on delete cascade,
    depth          text not null check (depth in ('index','overview','synthesis','details')),
    version        integer not null,
    content        text not null,
    source_refs    jsonb not null default '[]'::jsonb,     -- [{"kind":"log","session":…,"seq":…}, {"kind":"derived","id":…}]
    watermark      timestamptz,                            -- newest source taken into account
    fresh_until    timestamptz,
    builder        text not null,                          -- processor@version
    model          text,                                   -- the route that wrote it (Walter Router poste)
    privacy_class  text not null default 'cloud_allowed'
                   check (privacy_class in ('local_only','redacted_cloud','cloud_allowed')),
    built_at       timestamptz not null default now(),
    primary key (view_key, depth, version)
);

create table if not exists views.member (
    session_id     text not null,                          -- walter_logs session of the exchange
    seq            bigint not null,                        -- walter_logs seq of the owner's message
    view_key       text not null references views.view (view_key) on delete cascade,
    occurred_at    timestamptz not null,
    runtime        text,
    attached_by    text not null,                          -- rule | decision | new | night
    confidence     real,
    primary key (session_id, seq)                          -- one subject per exchange; re-attachment updates it
);
create index if not exists member_view_time on views.member (view_key, occurred_at desc);

create table if not exists views.ledger (
    id             bigserial primary key,
    at             timestamptz not null default now(),
    view_key       text,
    action         text not null,                          -- create | attach | reattach | rebuild | merge | error
    detail         jsonb not null default '{}'::jsonb
);

create table if not exists views.cursor (
    name           text primary key,
    position       timestamptz not null,
    updated_at     timestamptz not null default now()
);

-- Walter Memory P1 — foundation (2026-10-01).
-- Spec: /root/.hermes/docs/walter-memory/ARCHITECTURE.md (+ amendments A1–A9), PLAN.md §P1.
-- Truth = core.events (append-only) + core.objects (Raw Vault registry). Everything else is derived.
begin;

create schema if not exists core;
create schema if not exists ingestion;
create schema if not exists system;
create schema if not exists legacy;
comment on schema core is 'Walter Memory canonical layer: events (append-only truth), objects (Raw Vault registry), identities, entities, relationships, derived items, provenance.';
comment on schema ingestion is 'Walter Memory ingestion: connectors, checkpoints, job queue (SKIP LOCKED), failures, reconciliation.';
comment on schema system is 'Walter Memory operations: processors, model calls, budgets, audit log, break-glass purges.';
comment on schema legacy is 'Retired pre-2026-10 memory pipeline tables (Qdrant/jarvis era), kept read-only for provenance.';

-- ───────────────────────────── sources & taxonomy ─────────────────────────────
create table if not exists core.sources (
    source          text primary key,                 -- connector family: hermes, beeper, gmail, calendar, vault...
    kind            text not null,                    -- messaging | email | calendar | files | agent | location | web | legacy
    description     text,
    privacy_default text not null default 'cloud_allowed'
                    check (privacy_default in ('local_only','redacted_cloud','cloud_allowed')),
    config          jsonb not null default '{}',
    created_at      timestamptz not null default now()
);

-- A3: controlled, versioned, extensible taxonomy (a row, not an enum: new type = insert, no migration)
create table if not exists core.event_types (
    name        text not null check (name ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'),
    version     int  not null default 1,
    status      text not null default 'active' check (status in ('active','deprecated')),
    description text not null,
    json_schema jsonb not null default '{"type":"object"}',  -- validates payload (lib + gateway)
    created_at  timestamptz not null default now(),
    primary key (name, version)
);

-- ───────────────────────────── identities & entities ─────────────────────────────
-- A4: the actor as the source knows it, recorded at ingestion even before entity resolution.
create table if not exists core.source_identities (
    identity_id  uuid primary key default gen_random_uuid(),
    source       text not null references core.sources(source),
    account      text not null default '',            -- network/account inside the source: whatsapp, instagramgo, gmail:lucas…
    external_id  text not null,                       -- id in the source (Matrix user id, e-mail address, phone…)
    display_name text,
    handles      jsonb not null default '{}',
    phones       text[] not null default '{}',
    emails       text[] not null default '{}',
    is_self      boolean not null default false,      -- Monsieur himself on that account
    attributes   jsonb not null default '{}',
    first_seen   timestamptz not null default now(),
    last_seen    timestamptz not null default now(),
    unique (source, account, external_id)
);
create index if not exists source_identities_name on core.source_identities using gin (to_tsvector('simple', coalesce(display_name,'')));

create table if not exists core.entities (
    entity_id      uuid primary key default gen_random_uuid(),
    entity_type    text not null,                     -- person | organisation | place | project | product | account | event | object…
    canonical_name text not null,
    aliases        text[] not null default '{}',
    attributes     jsonb not null default '{}',
    status         text not null default 'active' check (status in ('active','merged','inactive')),
    merged_into    uuid references core.entities(entity_id),
    kardex_contact_id int,                            -- link to kardex.contacts for people (Kardex = social layer)
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);
create index if not exists entities_type_name on core.entities (entity_type, lower(canonical_name));

-- identity → entity is a derived, revisable fact
create table if not exists core.identity_links (
    identity_id uuid not null references core.source_identities(identity_id) on delete cascade,
    entity_id   uuid not null references core.entities(entity_id) on delete cascade,
    status      text not null default 'proposed' check (status in ('proposed','confirmed','rejected')),
    confidence  real not null default 0.5,
    method      text not null,                        -- strong_signal | manual | name_match | llm …
    provenance  jsonb not null default '{}',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    primary key (identity_id, entity_id)
);

create table if not exists core.relationships (
    relationship_id uuid primary key default gen_random_uuid(),
    subject_id  uuid not null references core.entities(entity_id) on delete cascade,
    predicate   text not null,                        -- knows | works_at | lives_in | member_of | partner_of …
    object_id   uuid not null references core.entities(entity_id) on delete cascade,
    valid_from  timestamptz,
    valid_to    timestamptz,
    confidence  real not null default 0.5,
    status      text not null default 'derived' check (status in ('derived','confirmed','retracted','legacy_derived')),
    derived_by  text, processor_version text,
    source_event_ids uuid[] not null default '{}',
    created_at  timestamptz not null default now()
);
create index if not exists relationships_subject on core.relationships (subject_id, predicate);
create index if not exists relationships_object on core.relationships (object_id, predicate);

-- ───────────────────────────── objects (A5: single registry) ─────────────────────────────
-- vault.objects / vault.links (created earlier today) become core.objects / core.object_links;
-- vault.* stay as updatable views so existing callers keep working during the transition.
-- On a blank database (Walter Clean, 2026-10-29) there is no vault.* to move: the same tables, constraints and indexes
-- are created directly. The relkind test reads pg_class through to_regclass so it never casts a missing name.
create schema if not exists vault;
do $$
begin
  if (select relkind from pg_class where oid = to_regclass('vault.objects')) = 'r' then
    alter table vault.objects set schema core;
    alter table vault.links rename to object_links;
    alter table vault.object_links set schema core;
  end if;
end $$;
create table if not exists core.objects (            -- no-op when migrated above
    id uuid primary key default gen_random_uuid(), sha256 text not null unique, size_bytes bigint not null,
    mime text, kind text not null
        check (kind in ('image','video','audio','document','screenshot','archive','other')),
    storage_key text not null, original_name text, captured_at timestamptz,
    source text not null, source_ref jsonb not null default '{}', meta jsonb not null default '{}',
    derived_text text, derived_kind text check (derived_kind in ('ocr','transcript','caption','extract')),
    derived_model text, derived_at timestamptz,
    status text not null default 'stored' check (status in ('stored','derived','retained','error')),
    ingested_at timestamptz not null default now());
create table if not exists core.object_links (       -- no-op when migrated above (vault.links keeps its key names)
    object_id   uuid not null,
    target_type text not null check (target_type ~ '^[a-z_]+$'),
    target_id   text not null,
    role        text not null default 'appears_in',
    constraint links_pkey primary key (object_id, target_type, target_id, role),
    constraint links_object_id_fkey foreign key (object_id) references core.objects(id) on delete cascade);
create index if not exists objects_captured on core.objects (captured_at desc);
create index if not exists objects_derived_fts on core.objects
    using gin (to_tsvector('french', coalesce(derived_text, '') || ' ' || coalesce(original_name, '')));
create index if not exists objects_pending on core.objects (status) where status <> 'retained';
create index if not exists objects_source on core.objects (source, kind);
alter table core.objects add column if not exists privacy_class text not null default 'cloud_allowed'
    check (privacy_class in ('local_only','redacted_cloud','cloud_allowed'));
alter table core.objects add column if not exists storage_zone text not null default 'clear'
    check (storage_zone in ('clear','secure'));        -- secure = encrypted Raw Vault zone (P1.5)
alter table core.objects add column if not exists derived_processor text;
alter table core.objects add column if not exists purged_at timestamptz;
create or replace view vault.objects as select * from core.objects;
create or replace view vault.links as select * from core.object_links;
comment on view vault.objects is 'Compatibility view (2026-10-01): the single object registry is core.objects (A5).';

-- ───────────────────────────── canonical events ─────────────────────────────
-- Global idempotence key (partitioned tables cannot carry a unique key without the partition column).
create table if not exists core.event_keys (
    source     text not null,
    source_id  text not null,
    event_type text not null,
    event_id   uuid not null,
    occurred_at timestamptz not null,
    primary key (source, source_id, event_type)
);
create unique index if not exists event_keys_event on core.event_keys (event_id);

create table if not exists core.events (
    event_id        uuid not null default gen_random_uuid(),
    event_type      text not null,
    type_version    int  not null default 1,
    source          text not null,
    source_account  text not null default '',
    source_id       text not null,
    occurred_at     timestamptz not null,
    ingested_at     timestamptz not null default now(),
    actor_identity_id uuid,                           -- core.source_identities (A4)
    thread_id       text,                             -- conversation/thread in the source (Hermes session, Beeper chat…)
    reply_to        text,                             -- source_id of the event this replies to
    content         text,
    content_hash    text,
    object_refs     uuid[] not null default '{}',     -- core.objects
    payload         jsonb not null default '{}',      -- validated against core.event_types.json_schema
    privacy_class   text not null default 'cloud_allowed'
                    check (privacy_class in ('local_only','redacted_cloud','cloud_allowed')),
    epistemic_status text not null default 'observed' check (epistemic_status = 'observed'),  -- A2: derived data never lives here
    schema_version  int  not null default 1,
    primary key (event_id, occurred_at)
) partition by range (occurred_at);
create index if not exists events_type_time   on core.events (event_type, occurred_at desc);
create index if not exists events_thread_time on core.events (source, thread_id, occurred_at);
create index if not exists events_actor_time  on core.events (actor_identity_id, occurred_at desc);
create index if not exists events_ingested    on core.events (ingested_at);
create index if not exists events_payload     on core.events using gin (payload jsonb_path_ops);
create table if not exists core.events_default partition of core.events default;

create or replace function core.ensure_event_partition(ts timestamptz) returns text language plpgsql as $$
declare
  m date := date_trunc('month', ts at time zone 'UTC')::date;
  name text := format('events_%s', to_char(m, 'YYYY_MM'));
begin
  if to_regclass('core.' || name) is null then
    execute format('create table core.%I partition of core.events for values from (%L) to (%L)',
                   name, (m::timestamp at time zone 'UTC'), ((m + interval '1 month')::timestamp at time zone 'UTC'));
  end if;
  return name;
end $$;

-- Append-only (A9): no UPDATE/DELETE except inside an explicit break-glass purge transaction.
create or replace function core.forbid_event_mutation() returns trigger language plpgsql as $$
begin
  if coalesce(current_setting('walter.purge', true), '') = 'on' then
    return case when tg_op = 'DELETE' then old else new end;
  end if;
  raise exception 'core.% is append-only: emit a correcting event (*.corrected / *.retracted) or use break-glass purge', tg_table_name;
end $$;
drop trigger if exists events_append_only on core.events;
create trigger events_append_only before update or delete on core.events
    for each row execute function core.forbid_event_mutation();
drop trigger if exists event_keys_append_only on core.event_keys;
create trigger event_keys_append_only before update or delete on core.event_keys
    for each row execute function core.forbid_event_mutation();

-- ───────────────────────────── derived items & provenance (A2) ─────────────────────────────
create table if not exists core.derived_items (
    item_id      uuid primary key default gen_random_uuid(),
    kind         text not null,                       -- fact | preference | decision | summary | memory | observation | open_loop | profile
    content      text not null,
    attributes   jsonb not null default '{}',
    status       text not null check (status in ('legacy_derived','derived','verified','retracted')),
    derived_by   text not null,                       -- processor name, or the legacy system it was imported from
    processor_version text,
    model        text,
    prompt_hash  text,
    source_event_ids  uuid[] not null default '{}',
    source_object_ids uuid[] not null default '{}',
    source_refs  jsonb not null default '{}',         -- external provenance (e.g. hindsight unit/document ids, state.db session)
    subject_entity_ids uuid[] not null default '{}',
    confidence   real,
    valid_from   timestamptz,
    valid_to     timestamptz,
    privacy_class text not null default 'cloud_allowed'
                  check (privacy_class in ('local_only','redacted_cloud','cloud_allowed')),
    created_at   timestamptz not null default now()
);
create unique index if not exists derived_items_ref on core.derived_items (derived_by, (source_refs->>'ref')) where source_refs ? 'ref';
create index if not exists derived_kind_status on core.derived_items (kind, status);
create index if not exists derived_source_events on core.derived_items using gin (source_event_ids);
-- A2: legacy_derived can only be retracted, never promoted automatically (verification = explicit, by Monsieur).
create or replace function core.guard_legacy_promotion() returns trigger language plpgsql as $$
begin
  if old.status = 'legacy_derived' and new.status not in ('legacy_derived','retracted')
     and coalesce(current_setting('walter.verify', true), '') <> 'on' then
    raise exception 'legacy_derived items cannot be promoted automatically (A2)';
  end if;
  return new;
end $$;
drop trigger if exists derived_legacy_guard on core.derived_items;
create trigger derived_legacy_guard before update on core.derived_items
    for each row execute function core.guard_legacy_promotion();

create table if not exists core.provenance (            -- generic link for derived rows living outside core (Kardex, Hindsight…)
    target_table text not null,
    target_id    text not null,
    source_type  text not null check (source_type in ('event','object','derived','external')),
    source_id    text not null,
    role         text not null default 'supports',
    created_at   timestamptz not null default now(),
    primary key (target_table, target_id, source_type, source_id, role)
);

-- ───────────────────────────── ingestion ─────────────────────────────
create table if not exists ingestion.connectors (
    connector   text primary key,                     -- beeper, hermes, gmail:lucas, calendar:lucas …
    source      text not null references core.sources(source),
    mode        text not null check (mode in ('push','pull','agent','import')),
    description text,
    enabled     boolean not null default true,
    freshness_target interval,
    last_success_at timestamptz,
    last_error  text,
    last_error_at timestamptz,
    created_at  timestamptz not null default now()
);
create table if not exists ingestion.checkpoints (
    connector  text not null references ingestion.connectors(connector),
    stream     text not null default '',              -- e.g. one Beeper chat, one mailbox label
    cursor     jsonb not null default '{}',
    last_item_at timestamptz,
    updated_at timestamptz not null default now(),
    primary key (connector, stream)
);
create table if not exists ingestion.jobs (
    job_id      bigserial primary key,
    queue       text not null,
    payload     jsonb not null default '{}',
    dedupe_key  text unique,
    priority    int not null default 100,             -- lower runs first
    status      text not null default 'queued' check (status in ('queued','running','done','failed','dead')),
    attempts    int not null default 0,
    max_attempts int not null default 5,
    run_after   timestamptz not null default now(),
    locked_by   text,
    locked_at   timestamptz,
    last_error  text,
    created_at  timestamptz not null default now(),
    finished_at timestamptz
);
create index if not exists jobs_ready on ingestion.jobs (queue, priority, run_after) where status = 'queued';
create table if not exists ingestion.failures (
    failure_id bigserial primary key,
    connector  text,
    stream     text,
    item_ref   text,
    error      text not null,
    details    jsonb not null default '{}',
    created_at timestamptz not null default now(),
    resolved_at timestamptz
);
create table if not exists ingestion.reconciliation_runs (
    run_id     bigserial primary key,
    connector  text not null,
    stream     text not null default '',
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    source_count bigint, walter_count bigint, gaps bigint, repaired bigint,
    details    jsonb not null default '{}'
);

-- ───────────────────────────── system ─────────────────────────────
create table if not exists system.processors (
    name text not null, version text not null, description text, prompt_hash text,
    created_at timestamptz not null default now(), primary key (name, version));
create table if not exists system.budgets (                -- D6: recurring vs exceptional (backfill/reprocessing)
    budget text primary key check (budget in ('recurring','backfill')),
    monthly_limit_usd numeric(10,2) not null,
    hard_stop boolean not null default true,
    notes text);
create table if not exists system.model_calls (
    call_id    bigserial primary key,
    at         timestamptz not null default now(),
    processor  text, processor_version text,
    provider   text, model text not null,
    purpose    text,
    budget     text not null default 'recurring' references system.budgets(budget),
    privacy_class text not null,
    input_tokens int, cached_tokens int, output_tokens int,
    cost_usd   numeric(12,6),
    latency_ms int,
    status     text not null,                          -- ok | error | refused_privacy | refused_budget
    error      text);
create index if not exists model_calls_month on system.model_calls (budget, at);
create table if not exists system.audit_log (
    audit_id bigserial primary key, at timestamptz not null default now(),
    actor text not null, action text not null, target text, details jsonb not null default '{}');
create table if not exists system.purges (                 -- A9: who/when/why/what (fingerprints only, never content)
    purge_id   bigserial primary key,
    at         timestamptz not null default now(),
    requested_by text not null,
    reason     text not null,
    selector   jsonb not null,                         -- how targets were selected (ids / pattern hash), no content
    fingerprints text[] not null default '{}',         -- sha256 of purged ids
    counts     jsonb not null default '{}',
    backups_rewritten boolean not null default false,
    status     text not null check (status in ('dry_run','executed','failed')));

-- ───────────────────────────── seeds ─────────────────────────────
insert into system.budgets (budget, monthly_limit_usd, notes) values
  ('recurring', 30, 'Default; to be confirmed by Monsieur (D6).'),
  ('backfill', 50, 'Exceptional backfill/reprocessing envelope; per-run approval for large runs (D6).')
on conflict do nothing;

insert into core.sources (source, kind, description, privacy_default) values
  ('hermes',   'agent',     'Conversations with W.Alter (Hermes state.db → core.events), tools and skills metadata', 'cloud_allowed'),
  ('beeper',   'messaging', 'Beeper Desktop API on Monsieur''s Mac: WhatsApp, Instagram, Messenger, Telegram, LINE, Signal…', 'redacted_cloud'),
  ('gmail',    'email',     'Gmail (read-only)', 'redacted_cloud'),
  ('calendar', 'calendar',  'Google Calendar (read-only)', 'cloud_allowed'),
  ('vault',    'files',     'Raw Vault uploads (files sent to W.Alter, imports)', 'cloud_allowed'),
  ('kardex_legacy', 'legacy', 'Messages collected by the pre-2026-10 Kardex pipelines (Beeper API, Instagram export)', 'redacted_cloud'),
  ('hindsight_legacy', 'legacy', 'Hindsight memories/documents created before Walter Memory (derived, A2)', 'cloud_allowed'),
  ('location', 'location',  'Device location samples', 'local_only'),
  ('claude',   'agent',     'Facts recorded by Claude sessions through walter-core', 'cloud_allowed')
on conflict do nothing;

-- ───────────────────────────── legacy tables out of the Hindsight namespace ─────────────────────────────
do $$
declare t text;
begin
  foreach t in array array['memory_facts','memory_outbox','units_sync_state','hindsight_edges','hindsight_episodes',
      'hindsight_fact_entities','hindsight_fact_provenance','current_beliefs','decision_rules','preferences',
      'project_states','access_audit_log','action_requests','memory_events'] loop
    if to_regclass('public.' || t) is not null then
      execute format('alter table public.%I set schema legacy', t);
    end if;
  end loop;
end $$;

commit;

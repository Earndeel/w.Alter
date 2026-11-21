-- Memory V1, event-driven assimilation (2026-11-03, Monsieur: « event-driven, incrémental, idempotent et traçable »).
-- P1.4-P1.6 (flows, plans, episodes, periods) were rebuilt on a 10-minute clock over whole windows: unchanged rows were
-- rewritten, a processor's marker stored in another processor's rows was erased, and model decisions were not kept,
-- so the same questions went back to the models. Fix, on the existing bus (no second event system):
--   1. every change of a V1 knowledge item is published on the bus (memory.derived), in the writing transaction,
--      only when something meaningful changed (a no-op update publishes nothing);
--   2. processing state lives apart from the knowledge it produces: processing.queue = what must be (re)computed,
--      keyed per processor (coalesced, settle/deadline, retries); processing.decisions = every model decision with its
--      exact inputs hash and its outcome, negative ones included, so an unchanged input never reaches a model twice;
--   3. the new consumer memory.organic starts at the current end of the bus (history is covered by reconciliation).
begin;

create schema if not exists processing;
comment on schema processing is 'Walter Memory processing state (2026-11-03): what must be recomputed (queue) and what the models already decided (decisions). Never knowledge: core.derived_items and views.* hold what was produced.';

create table if not exists processing.queue (
    processor   text not null,
    key         text not null,
    range_from  timestamptz,
    range_to    timestamptz,
    reason      text,
    dirty_since timestamptz not null default now(),
    due_at      timestamptz not null default now(),
    rev         bigint not null default 1,
    attempts    integer not null default 0,
    last_error  text,
    updated_at  timestamptz not null default now(),
    primary key (processor, key)
);
create index if not exists queue_due on processing.queue (due_at);
comment on table processing.queue is 'dirty keys per processor, set by bus events (memory.event / memory.derived / memory.view): coalesced (one row per key, time range widened), due after a settle delay or at a deadline, retried with backoff; a row is removed only if no new mark arrived while it was processed (rev)';

create table if not exists processing.decisions (
    processor     text not null,
    version       text not null,
    inputs_hash   text not null,
    input_key     text,
    refs          uuid[] not null default '{}',
    outcome       jsonb not null,
    model         text,
    privacy_class text not null check (privacy_class in ('local_only', 'redacted_cloud', 'cloud_allowed')),
    decided_at    timestamptz not null default now(),
    hits          integer not null default 0,
    last_hit_at   timestamptz,
    primary key (processor, version, inputs_hash)
);
create index if not exists decisions_refs on processing.decisions using gin (refs);
create index if not exists decisions_key on processing.decisions (processor, input_key);
comment on table processing.decisions is 'model decisions keyed by the exact inputs sent (sha256) and the processor version: the outcome is reused while the inputs are unchanged, negative outcomes included; refs = canonical events / knowledge items the inputs came from (purge, provenance); hits = reuses';

create table if not exists processing.stats (
    processor text not null,
    hour      timestamptz not null,
    keys      integer not null default 0,
    changed   integer not null default 0,
    calls     integer not null default 0,
    hits      integer not null default 0,
    errors    integer not null default 0,
    primary key (processor, hour)
);
comment on table processing.stats is 'per processor and hour: keys processed, outputs changed, model calls made, decisions reused, errors (before/after measurements, health)';

-- V1 knowledge changes → bus (memory.derived). Pre-V1 generations publish nothing.
create or replace function core.publish_derived() returns trigger language plpgsql as $$
begin
    if new.generation is distinct from 'g1' then
        return null;
    end if;
    if tg_op = 'UPDATE' and (new.content, new.status, new.attributes, new.valid_from, new.valid_to, new.privacy_class,
                             new.stage, new.epistemic, new.scope, new.source_event_ids, new.subject_entity_ids)
                            is not distinct from
                            (old.content, old.status, old.attributes, old.valid_from, old.valid_to, old.privacy_class,
                             old.stage, old.epistemic, old.scope, old.source_event_ids, old.subject_entity_ids) then
        return null;
    end if;
    insert into bus.events (type, source, subject, payload)
    values ('memory.derived', 'memory', new.item_id::text,
            jsonb_build_object('op', lower(tg_op), 'kind', new.kind, 'derived_by', new.derived_by,
                               'status', new.status, 'old_status', case when tg_op = 'UPDATE' then old.status end,
                               'epistemic', new.epistemic, 'privacy_class', new.privacy_class,
                               'at', coalesce(new.valid_from, new.created_at),
                               'old_at', case when tg_op = 'UPDATE' then coalesce(old.valid_from, old.created_at) end,
                               'end', new.attributes->>'end',
                               'owner_messages', new.attributes->>'owner_messages'));
    return null;
end $$;
comment on function core.publish_derived() is 'publishes each meaningful change of a V1 (g1) knowledge item as bus memory.derived in the writing transaction; a no-op update publishes nothing';
drop trigger if exists derived_publish on core.derived_items;
create trigger derived_publish after insert or update on core.derived_items
    for each row execute function core.publish_derived();

-- The organic consumer starts at the current end of the bus: the past is covered by reconciliation, not replayed.
insert into bus.cursors (consumer, last_tx, last_id)
select 'memory.organic', e.tx, e.id from bus.events e order by e.tx desc, e.id desc limit 1
on conflict (consumer) do nothing;

commit;

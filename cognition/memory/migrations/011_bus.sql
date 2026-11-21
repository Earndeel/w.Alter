-- Walter bus (2026-10-10): one event bus for every Walter module — instant and durable, no new infrastructure.
-- Producers (runtime hooks = adapters, module doors, connectors) append typed events; an insert trigger wakes
-- listeners with pg_notify; each consumer keeps a cursor, so a consumer that was down catches up from the table.
-- Delivery is at-least-once: handlers are idempotent. Failed handlings are kept in bus.dead (the cursor moves on).
begin;
create schema if not exists bus;
comment on schema bus is 'Walter event bus: append-only typed events + LISTEN/NOTIFY wake-ups + per-consumer cursors';

create table if not exists bus.events (
    id          bigserial primary key,
    at          timestamptz not null default now(),
    type        text not null,              -- skill.proposed, skill.changed, turn.ended, session.ended, …
    source      text not null,              -- who emitted: claude_code, hermes, dsh, codex, walter-skills, …
    subject     text,                       -- what it is about (skill name, session id …)
    payload     jsonb not null default '{}',
    dedupe_key  text unique                 -- optional: the same fact emitted twice is stored once
);
create index if not exists events_type_id on bus.events (type, id);

create table if not exists bus.cursors (
    consumer    text primary key,
    last_id     bigint not null default 0,
    updated_at  timestamptz not null default now()
);

create table if not exists bus.dead (
    consumer    text not null,
    event_id    bigint not null references bus.events(id),
    at          timestamptz not null default now(),
    error       text,
    primary key (consumer, event_id)
);

create or replace function bus.notify() returns trigger language plpgsql as $$
begin
    perform pg_notify('walter_bus', new.type || ':' || new.id);
    return new;
end $$;
drop trigger if exists events_notify on bus.events;
create trigger events_notify after insert on bus.events for each row execute function bus.notify();
commit;

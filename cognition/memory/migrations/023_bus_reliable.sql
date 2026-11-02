-- Walter bus, reliable delivery (2026-11-02, Memory V1 P0).
--
-- 1. Gap-free cursors. `bigserial` ids are allocated when a row is inserted, not when its transaction commits: a
--    transaction that inserted id 10 can commit after one that inserted id 11, and a cursor at 11 never sees 10.
--    Each row now records its top-level transaction id (`tx`, xid8). A consumer only reads rows whose transaction is
--    older than the oldest transaction still running (pg_snapshot_xmin of the current snapshot): every such
--    transaction has finished, so no row can appear later below the cursor. Cursors move on (tx, id). Cost: a
--    transaction that stays open delays delivery (never loses it); `bus.lag` reports it.
--    Rows written before this migration get tx = 0 and keep their id order.
-- 2. Retries with backoff: a failed handling goes to bus.dead with status 'retrying' and next_at; the consumer retries
--    it until max attempts, then 'dead'. `walter-memory bus replay` puts dead letters back.
-- 3. Every new canonical event is published on the bus in the same transaction as its insertion (memory.event), so a
--    committed event can never miss its notification; consumers read the table, the NOTIFY is only a wake-up.
begin;

alter table bus.events add column if not exists tx xid8;
update bus.events set tx = '0'::xid8 where tx is null;
alter table bus.events alter column tx set default pg_current_xact_id();
alter table bus.events alter column tx set not null;
create index if not exists events_tx_id on bus.events (tx, id);
create index if not exists events_type_tx_id on bus.events (type, tx, id);
comment on column bus.events.tx is 'top-level transaction id of the insert: consumers read only rows of finished transactions (gap-free cursors)';

alter table bus.cursors add column if not exists last_tx xid8 not null default '0'::xid8;
comment on column bus.cursors.last_tx is 'cursor position = (last_tx, last_id) in bus.events (tx, id) order';

alter table bus.dead add column if not exists attempts integer not null default 1;
alter table bus.dead add column if not exists status text not null default 'dead';
alter table bus.dead add column if not exists next_at timestamptz;
alter table bus.dead add column if not exists resolved_at timestamptz;
alter table bus.dead drop constraint if exists dead_status_check;
alter table bus.dead add constraint dead_status_check check (status in ('retrying', 'dead', 'resolved'));
create index if not exists dead_retry on bus.dead (consumer, next_at) where status = 'retrying';
comment on column bus.dead.status is 'retrying (next_at = next attempt) → resolved, or dead after max attempts (walter-memory bus replay)';

-- core.events → bus: one memory.event per inserted canonical event, same transaction.
create or replace function core.publish_event() returns trigger language plpgsql as $$
begin
    insert into bus.events (type, source, subject, payload, dedupe_key)
    values ('memory.event', 'memory', new.event_id::text,
            jsonb_build_object('event_type', new.event_type, 'source', new.source,
                               'source_account', new.source_account, 'thread_id', new.thread_id,
                               'occurred_at', new.occurred_at, 'privacy_class', new.privacy_class),
            'memory.event:' || new.event_id::text)
    on conflict (dedupe_key) do nothing;
    return null;
end $$;
comment on function core.publish_event() is 'publishes each new canonical event as bus memory.event in the inserting transaction (outbox)';
drop trigger if exists events_publish on core.events;
create trigger events_publish after insert on core.events for each row execute function core.publish_event();

commit;

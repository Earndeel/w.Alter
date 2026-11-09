-- Memory cleanup phase 2 (Monsieur's go of 2026-11-09; plan: docs/NETTOYAGE-2026-11.md § phase 2).
--
-- 1. Observability leaves core.events. walter_logs is the canonical journal of what agents executed (every tool call,
--    its full arguments and result); core.events keeps the events and observations useful to memory. The two
--    observability types the connectors used to copy into core.events are retired: the write door
--    (walter_memory.types) refuses a retired type, so no connector can recreate the copies. Historical rows are
--    removed separately by `walter-memory observability retire` (a traced Memory operation, never a bare delete).
-- 2. Purge ledger: what every executed purge removed, by identifier only (never content), so that a purge can be
--    re-applied after any restore (`walter-memory purge reapply`) and its reappearance detected (`purge verify`,
--    walter-memory health). An external copy lives in the instance (@instance/state/memory/purge-ledger.jsonl): a
--    restored database predating the purge does not carry this table.
-- Idempotent: a blank or test database passes through unchanged.
begin;
set local lock_timeout = '5s';

-- 'deprecated' still accepts writes; 'retired' is refused by the write door
alter table core.event_types drop constraint if exists event_types_status_check;
alter table core.event_types add constraint event_types_status_check
  check (status in ('active', 'deprecated', 'retired'));

update core.event_types set status = 'retired'
 where name in ('tool.called', 'skill.used') and status = 'active';

create table if not exists system.purge_ledger (
  purge_id  bigint not null references system.purges (purge_id),
  kind      text   not null check (kind in ('event', 'derived', 'object', 'walter_logs', 'operation')),
  target    text   not null,
  at        timestamptz not null default now(),
  primary key (kind, target)
);
comment on table system.purge_ledger is
  'What each executed purge removed, by identifier only (event_id, item_id, object id, walter_logs session_id#event_key, '
  'or an operation name that re-runs itself): re-applied after a restore by `walter-memory purge reapply`, checked by '
  '`walter-memory purge verify` and health. Mirrored outside the database in @instance/state/memory/purge-ledger.jsonl.';

commit;

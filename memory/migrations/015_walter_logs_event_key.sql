-- walter-logs idempotence on the event's identity, not its position in the source (2026-10-25).
-- (session_id, source_ref) only knew positions (Hermes row id, transcript byte offset). Runtimes write the same event
-- again under a new position: Claude Code re-appends transcript lines (same uuid) on resume, Hermes re-persists history
-- rows under new ids in state.db, a rewritten transcript shifts every offset. ~41k duplicated rows on 25/10.
-- event_key = walter_memory.logs.event_key(): hash of type, instant, part inside the source item, call, tool, stored
-- text and data. Backfill: `connectors/walter_logs.py keys` (the first copy of each event gets the key; later copies
-- keep NULL until the cleanup decided with Monsieur, DECISIONS.md 2026-10-25).
alter table walter_logs.events add column if not exists event_key text;
comment on column walter_logs.events.event_key is
  'Identity of the event inside its session, independent of its position in the source (logs.event_key()). Unique per session.';
create unique index if not exists events_key on walter_logs.events (session_id, event_key) where event_key is not null;

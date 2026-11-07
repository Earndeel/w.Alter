"""Walter bus — events instead of timers, for every Walter module.

  emit(type, source, subject, payload)     one insert; the trigger wakes listeners (pg_notify 'walter_bus')
  emit(..., conn=c)                        inside the caller's transaction: published if and only if it commits
  Consumer(name, types).run(handler)       catch up from its cursor, then LISTEN; at-least-once, idempotent handlers;
                                           a failing event is retried with backoff (bus.dead 'retrying'), then 'dead'
  Consumer(..., settle=s).run(batch_handler, batch=True)
                                           wait `s` seconds of calm after a wake-up, then hand every pending event over
                                           at once (a burst of edits → one reaction)
  replay(consumer)                         dead letters back to 'retrying'
Emitting without `conn` never raises (fail-open): a runtime hook must never block an agent because the bus is down.

Delivery is gap-free (migration 023): a consumer reads only rows whose inserting transaction is older than every
transaction still running, in (tx, id) order, so a transaction that commits late can never fall behind a cursor.
New canonical events arrive as `memory.event` (subject = event_id), published by a trigger on core.events in the
inserting transaction. Handlers must be idempotent and tolerate order changes (retries are delivered later).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Callable, Iterable

import psycopg

from .db import DSN, connection

log = logging.getLogger("walter.bus")
CHANNEL = "walter_bus"
MAX_ATTEMPTS = 6
BACKOFF_S = (30, 120, 600, 1800, 7200, 21600)   # wait after attempt 1, 2, …; at MAX_ATTEMPTS the letter is 'dead'

# Rows of finished transactions only: the oldest running transaction bounds what can still appear below a cursor.
_FRONTIER = "e.tx < pg_snapshot_xmin(pg_current_snapshot())"
_COLS = "e.id, e.tx::text as tx, e.at, e.type, e.source, e.subject, e.payload"


def emit(type: str, source: str, subject: str | None = None, payload: dict | None = None,
         dedupe_key: str | None = None, conn=None) -> int | None:
    sql = """insert into bus.events (type, source, subject, payload, dedupe_key) values (%s, %s, %s, %s, %s)
             on conflict (dedupe_key) do nothing returning id"""
    args = (type, source, subject, json.dumps(payload or {}, ensure_ascii=False, default=str), dedupe_key)
    if conn is not None:   # transactional: errors propagate, the event exists iff the caller commits
        row = conn.execute(sql, args).fetchone()
        return (row["id"] if isinstance(row, dict) else row[0]) if row else None
    try:
        with psycopg.connect(DSN, connect_timeout=3, autocommit=True) as c:  # hooks are short-lived processes
            row = c.execute(sql, args).fetchone()
        return row[0] if row else None
    except Exception as e:
        log.warning("bus emit failed (%s %s): %s", type, subject, e)
        return None


def backoff(attempts: int) -> int:
    return BACKOFF_S[max(1, min(attempts, len(BACKOFF_S))) - 1]


class Consumer:
    def __init__(self, name: str, types: Iterable[str], batch: int = 50, settle: float = 0.0,
                 max_attempts: int = MAX_ATTEMPTS):
        self.name, self.types, self.batch, self.settle = name, list(types), batch, settle
        self.max_attempts = max_attempts

    def _cursor(self) -> tuple[str, int]:
        with connection() as c:
            c.execute("insert into bus.cursors (consumer) values (%s) on conflict do nothing", (self.name,))
            r = c.execute("select last_tx::text as tx, last_id from bus.cursors where consumer = %s",
                          (self.name,)).fetchone()
            return r["tx"], r["last_id"]

    def _advance(self, ev: dict) -> None:
        with connection() as c:   # never backwards (a concurrent drain of the same consumer)
            c.execute("""update bus.cursors set last_tx = %s::xid8, last_id = %s, updated_at = now()
                         where consumer = %s and (last_tx, last_id) < (%s::xid8, %s)""",
                      (ev["tx"], ev["id"], self.name, ev["tx"], ev["id"]))

    def pending_after(self, after: tuple[str, int] | None) -> list[dict]:
        tx, last = after or self._cursor()
        with connection() as c:
            return c.execute(f"""select {_COLS} from bus.events e
                                 where (e.tx, e.id) > (%s::xid8, %s) and e.type = any(%s) and {_FRONTIER}
                                 order by e.tx, e.id limit %s""", (tx, last, self.types, self.batch)).fetchall()

    def pending(self) -> list[dict]:
        return self.pending_after(None)

    def _failed(self, events: list[dict], err: Exception) -> None:
        msg = f"{type(err).__name__}: {err}"[:1000]
        with connection() as c:
            for ev in events:
                c.execute("""insert into bus.dead (consumer, event_id, error, attempts, status, next_at)
                             values (%s, %s, %s, 1, case when %s <= 1 then 'dead' else 'retrying' end,
                                     now() + make_interval(secs => %s))
                             on conflict (consumer, event_id) do update set
                               error = excluded.error, at = now(), attempts = bus.dead.attempts + 1,
                               status = case when bus.dead.attempts + 1 >= %s then 'dead' else 'retrying' end,
                               next_at = now() + make_interval(secs => %s)""",
                          (self.name, ev["id"], msg, self.max_attempts, backoff(1), self.max_attempts, backoff(2)))

    def retry_due(self, handler: Callable, batch: bool = False) -> dict:
        """Re-run failed events whose next attempt is due. Success → resolved; failure → next backoff, or dead."""
        with connection() as c:
            due = c.execute(f"""select {_COLS}, d.attempts from bus.dead d join bus.events e on e.id = d.event_id
                                where d.consumer = %s and d.status = 'retrying' and d.next_at <= now()
                                order by e.tx, e.id limit 200""", (self.name,)).fetchall()
        out = {"retried": 0, "resolved": 0, "failed": 0}
        for ev in due:
            out["retried"] += 1
            try:
                handler([ev]) if batch else handler(ev)
            except Exception as e:
                out["failed"] += 1
                n = ev["attempts"] + 1
                with connection() as c:
                    c.execute("""update bus.dead set attempts = %s, error = %s, at = now(),
                                   status = case when %s >= %s then 'dead' else 'retrying' end,
                                   next_at = now() + make_interval(secs => %s)
                                 where consumer = %s and event_id = %s""",
                              (n, f"{type(e).__name__}: {e}"[:1000], n, self.max_attempts, backoff(n),
                               self.name, ev["id"]))
                continue
            out["resolved"] += 1
            with connection() as c:
                c.execute("""update bus.dead set status = 'resolved', resolved_at = now()
                             where consumer = %s and event_id = %s""", (self.name, ev["id"]))
        return out

    def drain(self, handler: Callable[[dict], None]) -> int:
        """Handle everything pending (catch-up). Returns the number of events handled. The cursor advances after each
        event: a crash re-delivers at most the event in hand."""
        n = 0
        while True:
            events = self.pending()
            if not events:
                return n
            for ev in events:
                try:
                    handler(ev)
                except Exception as e:  # poison event: retried later, never blocks the stream
                    log.exception("bus consumer %s failed on event %s", self.name, ev["id"])
                    self._failed([ev], e)
                self._advance(ev)
                n += 1

    def drain_batch(self, handler: Callable[[list[dict]], None], max_events: int = 5000) -> int:
        """Hand pending events to `handler` in one call (≤ max_events); on failure each of them is retried later."""
        total = 0
        while True:
            events: list[dict] = []
            while chunk := self.pending_after((events[-1]["tx"], events[-1]["id"]) if events else None):
                events += chunk
                if len(events) >= max_events:
                    break
            if not events:
                return total
            try:
                handler(events)
            except Exception as e:
                log.exception("bus consumer %s failed on a batch of %d", self.name, len(events))
                self._failed(events, e)
            self._advance(events[-1])
            total += len(events)
            if len(events) < max_events:
                return total

    def run(self, handler: Callable, idle: Callable[[], None] | None = None, idle_every: float = 3600.0,
            batch: bool = False) -> None:
        """Forever: drain, then sleep on LISTEN until an event (or `idle_every` → idle(), e.g. a reconciliation sweep).
        At least every minute it drains without a wake-up (rows that were held behind a long transaction become
        readable without a new notification) and retries due failures."""
        drain = (lambda: self.drain_batch(handler)) if batch else (lambda: self.drain(handler))
        last_idle = time.monotonic()
        while True:
            try:
                with psycopg.connect(DSN, autocommit=True) as conn:
                    conn.execute(f"listen {CHANNEL}")
                    drain()
                    while True:
                        woke = any(True for _ in conn.notifies(timeout=60, stop_after=1))
                        if woke and self.settle:  # let the burst finish (bounded: a steady stream can't starve us)
                            deadline = time.monotonic() + 6 * self.settle
                            while time.monotonic() < deadline and any(
                                    True for _ in conn.notifies(timeout=self.settle, stop_after=1)):
                                pass
                        drain()
                        self.retry_due(handler, batch)
                        if idle and time.monotonic() - last_idle > idle_every:
                            idle()
                            last_idle = time.monotonic()
                            drain()
            except Exception:
                log.exception("bus consumer %s: connection lost, retrying in 10 s", self.name)
                time.sleep(10)


def replay(consumer: str, event_id: int | None = None, status: str = "dead") -> int:
    """Put dead letters of a consumer (or one event) back into its retry queue: due now, attempts reset."""
    with connection() as c:
        rows = c.execute("""update bus.dead set status = 'retrying', next_at = now(), attempts = 0
                            where consumer = %s and (%s::bigint is null or event_id = %s) and status = %s
                            returning event_id""", (consumer, event_id, event_id, status)).fetchall()
    return len(rows)


def dead(consumer: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
    with connection() as c:
        return c.execute("""select d.consumer, d.event_id, e.type, e.subject, d.status, d.attempts, d.at, d.next_at,
                                   d.error from bus.dead d join bus.events e on e.id = d.event_id
                            where (%s::text is null or d.consumer = %s) and (%s::text is null or d.status = %s)
                            order by d.at desc limit %s""", (consumer, consumer, status, status, limit)).fetchall()


def lag(consumer: str, types: Iterable[str]) -> dict:
    """Health of one consumer: events readable and not yet handled, age of the oldest, events held behind a
    transaction still running (not yet readable by anyone), letters waiting for a retry, dead letters."""
    types = list(types)
    with connection() as c:
        c.execute("insert into bus.cursors (consumer) values (%s) on conflict do nothing", (consumer,))
        r = c.execute(f"""select extract(epoch from now() - min(e.at))::int as oldest_s, count(e.id) as pending
                          from bus.events e, bus.cursors k
                          where k.consumer = %s and e.type = any(%s) and (e.tx, e.id) > (k.last_tx, k.last_id)
                            and {_FRONTIER}""", (consumer, types)).fetchone()
        held = c.execute(f"""select count(*) as n from bus.events e
                             where e.type = any(%s) and not ({_FRONTIER})""", (types,)).fetchone()["n"]
        d = c.execute("""select count(*) filter (where status = 'retrying') as retrying,
                                count(*) filter (where status = 'dead') as dead,
                                count(*) filter (where at > now() - interval '24 hours' and status <> 'resolved') as dead_24h
                         from bus.dead where consumer = %s""", (consumer,)).fetchone()
    return {"pending": r["pending"], "oldest_s": r["oldest_s"] or 0, "held": held,
            "retrying": d["retrying"], "dead": d["dead"], "dead_24h": d["dead_24h"]}


def prune(days: int = 30) -> int:
    """Delete bus rows older than `days` that no unresolved letter references. A consumer more than `days` behind is
    already broken (its guardian says so); canonical events stay in core.events and reconciliation re-finds them."""
    with connection() as c:
        c.execute("delete from bus.dead where status = 'resolved' and resolved_at < now() - make_interval(days => %s)",
                  (days,))
        rows = c.execute("""delete from bus.events e
                            where e.at < now() - make_interval(days => %s)
                              and not exists (select 1 from bus.dead d where d.event_id = e.id)
                            returning e.id""", (days,)).fetchall()
    return len(rows)

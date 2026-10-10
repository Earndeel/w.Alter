"""Walter bus — events instead of timers, for every Walter module.

  emit(type, source, subject, payload)     one insert; the trigger wakes listeners (pg_notify 'walter_bus')
  Consumer(name, types).run(handler)       catch up from its cursor, then LISTEN; at-least-once, idempotent handlers;
                                           a failing event goes to bus.dead and the cursor moves on
  Consumer(..., settle=s).run(batch_handler, batch=True)
                                           wait `s` seconds of calm after a wake-up, then hand every pending event over
                                           at once (a burst of edits → one reaction)
Emitting never raises (fail-open): a runtime hook must never block an agent because the bus is down.
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


def emit(type: str, source: str, subject: str | None = None, payload: dict | None = None,
         dedupe_key: str | None = None) -> int | None:
    try:
        with psycopg.connect(DSN, connect_timeout=3, autocommit=True) as conn:  # hooks are short-lived processes
            row = conn.execute(
                """insert into bus.events (type, source, subject, payload, dedupe_key) values (%s, %s, %s, %s, %s)
                   on conflict (dedupe_key) do nothing returning id""",
                (type, source, subject, json.dumps(payload or {}, ensure_ascii=False, default=str), dedupe_key)).fetchone()
        return row[0] if row else None
    except Exception as e:
        log.warning("bus emit failed (%s %s): %s", type, subject, e)
        return None


class Consumer:
    def __init__(self, name: str, types: Iterable[str], batch: int = 50, settle: float = 0.0):
        self.name, self.types, self.batch, self.settle = name, list(types), batch, settle

    def _cursor(self) -> int:
        with connection() as c:
            c.execute("insert into bus.cursors (consumer) values (%s) on conflict do nothing", (self.name,))
            return c.execute("select last_id from bus.cursors where consumer = %s", (self.name,)).fetchone()["last_id"]

    def _advance(self, event_id: int) -> None:
        with connection() as c:
            c.execute("update bus.cursors set last_id = %s, updated_at = now() where consumer = %s", (event_id, self.name))

    def pending(self) -> list[dict]:
        with connection() as c:
            return c.execute("""select id, at, type, source, subject, payload from bus.events
                                where id > %s and type = any(%s) order by id limit %s""",
                             (self._cursor(), self.types, self.batch)).fetchall()

    def drain(self, handler: Callable[[dict], None]) -> int:
        """Handle everything pending (catch-up). Returns the number of events handled."""
        n = 0
        while True:
            events = self.pending()
            if not events:
                return n
            for ev in events:
                try:
                    handler(ev)
                except Exception as e:  # poison event: recorded, never blocks the stream
                    log.exception("bus consumer %s failed on event %s", self.name, ev["id"])
                    with connection() as c:
                        c.execute("""insert into bus.dead (consumer, event_id, error) values (%s, %s, %s)
                                     on conflict do nothing""", (self.name, ev["id"], f"{type(e).__name__}: {e}"[:1000]))
                self._advance(ev["id"])
                n += 1

    def drain_batch(self, handler: Callable[[list[dict]], None]) -> int:
        """Hand all pending events to `handler` in one call; on failure every event of the batch goes to bus.dead."""
        events: list[dict] = []
        while chunk := self.pending_after(events[-1]["id"] if events else None):
            events += chunk
        if not events:
            return 0
        try:
            handler(events)
        except Exception as e:
            log.exception("bus consumer %s failed on a batch of %d", self.name, len(events))
            with connection() as c:
                for ev in events:
                    c.execute("""insert into bus.dead (consumer, event_id, error) values (%s, %s, %s)
                                 on conflict do nothing""", (self.name, ev["id"], f"{type(e).__name__}: {e}"[:1000]))
        self._advance(events[-1]["id"])
        return len(events)

    def pending_after(self, after: int | None) -> list[dict]:
        if after is None:
            return self.pending()
        with connection() as c:
            return c.execute("""select id, at, type, source, subject, payload from bus.events
                                where id > %s and type = any(%s) order by id limit %s""",
                             (after, self.types, self.batch)).fetchall()

    def run(self, handler: Callable, idle: Callable[[], None] | None = None, idle_every: float = 3600.0,
            batch: bool = False) -> None:
        """Forever: drain, then sleep on LISTEN until an event (or `idle_every` → idle(), e.g. a reconciliation sweep).
        A notification for a type this consumer ignores costs one indexed query."""
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
                        if woke:
                            drain()
                        if idle and time.monotonic() - last_idle > idle_every:
                            idle()
                            last_idle = time.monotonic()
                            drain()
            except Exception:
                log.exception("bus consumer %s: connection lost, retrying in 10 s", self.name)
                time.sleep(10)


def lag(consumer: str, types: Iterable[str]) -> dict:
    """Health of one consumer: age of its oldest unhandled event (0 = up to date) and failures in the last 24 h."""
    with connection() as c:
        r = c.execute("""select extract(epoch from now() - min(e.at))::int as oldest_s, count(e.id) as pending
                         from bus.events e where e.type = any(%s)
                           and e.id > coalesce((select last_id from bus.cursors where consumer = %s), 0)""",
                      (list(types), consumer)).fetchone()
        dead = c.execute("select count(*) as n from bus.dead where consumer = %s and at > now() - interval '24 hours'",
                         (consumer,)).fetchone()["n"]
    return {"pending": r["pending"], "oldest_s": r["oldest_s"] or 0, "dead_24h": dead}

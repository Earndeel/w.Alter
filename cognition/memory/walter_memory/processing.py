"""Processing state of Walter Memory (2026-11-03): what must be recomputed, and what the models already decided.

Kept apart from the knowledge it produces (core.derived_items, views.*), so no processor ever stores its progress in
another processor's rows.

  mark(conn, processor, key, …)      a key becomes dirty: one row per (processor, key), the time range widens, the due
                                     time moves back by `settle` while marks keep coming (bounded by `max_wait`), or is
                                     set to a deadline (`due`)
  due(processor, now) / done / failed
                                     the worker takes due keys; a key is removed only if no mark arrived meanwhile (rev),
                                     a failure is retried with backoff (attempts, last_error) — nothing is lost on a crash
  decide_once(processor, version, inputs, call, …)
                                     a model decision keyed by the sha256 of its exact inputs and the processor version:
                                     reused while the inputs are unchanged, negative outcomes included; a failed call is
                                     never recorded (it is retried); refs = the events / items the inputs came from
  count(processor, …)                hourly counters (keys, changed, calls, hits, errors) for measurements and health
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .db import connection

log = logging.getLogger("walter.processing")
BACKOFF_S = (30, 120, 600, 1800, 7200)
MAX_ATTEMPTS = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


def mark(conn, processor: str, key: str, *, at_from: datetime | None = None, at_to: datetime | None = None,
         reason: str = "", settle: float = 0.0, max_wait: float | None = None, due: datetime | None = None) -> None:
    """Make (processor, key) dirty. `settle` s of calm before it is due (a burst of events → one computation), never
    later than `max_wait` s after it became dirty; `due` = an explicit deadline (the later of the two wins)."""
    max_wait = max_wait if max_wait is not None else max(settle * 6, 60.0)
    conn.execute(
        """insert into processing.queue as q (processor, key, range_from, range_to, reason, due_at)
           values (%(p)s, %(k)s, %(f)s, %(t)s, %(r)s,
                   greatest(now() + make_interval(secs => %(s)s), coalesce(%(d)s::timestamptz, '-infinity')))
           on conflict (processor, key) do update set
             range_from = least(q.range_from, excluded.range_from),
             range_to = greatest(q.range_to, excluded.range_to),
             reason = left(case when q.reason = excluded.reason or excluded.reason = '' then q.reason
                                else concat_ws(',', nullif(q.reason, ''), excluded.reason) end, 200),
             due_at = greatest(least(greatest(q.due_at, now() + make_interval(secs => %(s)s)),
                                     q.dirty_since + make_interval(secs => %(w)s)),
                               coalesce(%(d)s::timestamptz, '-infinity')),
             rev = q.rev + 1, updated_at = now()""",
        {"p": processor, "k": key, "f": at_from, "t": at_to or at_from, "r": reason[:60], "s": settle,
         "w": max_wait, "d": due})


def due(processor: str, now: datetime | None = None, limit: int = 200) -> list[dict]:
    with connection() as conn:
        return conn.execute("""select processor, key, range_from, range_to, reason, rev, attempts, dirty_since
                               from processing.queue where processor = %s and due_at <= %s
                               order by due_at, key limit %s""", (processor, now or _now(), limit)).fetchall()


def done(row: dict) -> bool:
    """Remove the key unless it was marked again while it was processed (then it stays, due as marked)."""
    with connection() as conn:
        r = conn.execute("""delete from processing.queue where processor = %s and key = %s and rev = %s returning 1""",
                         (row["processor"], row["key"], row["rev"])).fetchone()
        if not r:   # marked meanwhile: what was processed is done, the new range stays
            conn.execute("update processing.queue set attempts = 0, last_error = null where processor = %s and key = %s",
                         (row["processor"], row["key"]))
    return bool(r)


def failed(row: dict, err: Exception) -> None:
    n = row["attempts"] + 1
    wait = BACKOFF_S[min(n, len(BACKOFF_S)) - 1]
    with connection() as conn:
        conn.execute("""update processing.queue set attempts = %s, last_error = %s, due_at = now() + make_interval(secs => %s),
                          updated_at = now() where processor = %s and key = %s""",
                     (n, f"{type(err).__name__}: {err}"[:500], wait if n < MAX_ATTEMPTS else 86400,
                      row["processor"], row["key"]))


def inputs_hash(inputs: Any) -> str:
    return hashlib.sha256(json.dumps(inputs, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def decide_once(processor: str, version: str, inputs: Any, call: Callable[[], tuple[Any, str | None]], *,
                privacy_class: str, refs: list[str] | None = None, input_key: str | None = None) -> tuple[Any, bool]:
    """(outcome, reused). `call()` → (outcome, model) runs only when these exact inputs were never decided by this
    processor version. Exceptions propagate and nothing is recorded (the work is retried later)."""
    h = inputs_hash(inputs)
    with connection() as conn:
        r = conn.execute("""update processing.decisions set hits = hits + 1, last_hit_at = now()
                            where processor = %s and version = %s and inputs_hash = %s returning outcome""",
                         (processor, version, h)).fetchone()
    if r:
        count(processor, hits=1)
        return r["outcome"], True
    outcome, model = call()
    with connection() as conn:
        conn.execute("""insert into processing.decisions (processor, version, inputs_hash, input_key, refs, outcome, model,
                                                          privacy_class)
                        values (%s, %s, %s, %s, %s::uuid[], %s, %s, %s) on conflict do nothing""",
                     (processor, version, h, input_key, [str(x) for x in refs or []],
                      json.dumps(outcome, ensure_ascii=False, default=str), model, privacy_class))
    count(processor, calls=1)
    return outcome, False


def remember(processor: str, version: str, inputs: Any, outcome: Any, *, privacy_class: str, model: str | None = None,
             refs: list[str] | None = None, input_key: str | None = None) -> bool:
    """Record a decision taken elsewhere (e.g. before this ledger existed). True if it was new."""
    with connection() as conn:
        r = conn.execute("""insert into processing.decisions (processor, version, inputs_hash, input_key, refs, outcome,
                                                              model, privacy_class)
                            values (%s, %s, %s, %s, %s::uuid[], %s, %s, %s) on conflict do nothing returning 1""",
                         (processor, version, inputs_hash(inputs), input_key, [str(x) for x in refs or []],
                          json.dumps(outcome, ensure_ascii=False, default=str), model, privacy_class)).fetchone()
    return bool(r)


def count(processor: str, **n: int) -> None:
    cols = [c for c in ("keys", "changed", "calls", "hits", "errors") if n.get(c)]
    if not cols:
        return
    try:
        with connection() as conn:
            conn.execute(f"""insert into processing.stats (processor, hour, {', '.join(cols)})
                             values (%s, date_trunc('hour', now()), {', '.join(['%s'] * len(cols))})
                             on conflict (processor, hour) do update set
                             {', '.join(f'{c} = processing.stats.{c} + excluded.{c}' for c in cols)}""",
                         (processor, *[n[c] for c in cols]))
    except Exception as e:  # counters never break processing
        log.warning("processing stats: %s", e)


def backlog() -> list[dict]:
    with connection() as conn:
        return conn.execute("""select processor, count(*) as keys, count(*) filter (where due_at <= now()) as due,
                                      count(*) filter (where attempts > 0) as failing,
                                      extract(epoch from now() - min(dirty_since) filter (where due_at <= now()))::int
                                        as oldest_due_s
                               from processing.queue group by 1 order by 1""").fetchall()


def summary(hours: int = 24) -> list[dict]:
    with connection() as conn:
        return conn.execute("""select processor, sum(keys) keys, sum(changed) changed, sum(calls) calls, sum(hits) hits,
                                      sum(errors) errors
                               from processing.stats where hour >= now() - make_interval(hours => %s)
                               group by 1 order by 1""", (hours,)).fetchall()

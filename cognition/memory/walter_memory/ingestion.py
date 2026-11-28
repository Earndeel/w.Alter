"""Ingestion plumbing: connectors, checkpoints, job queue (FOR UPDATE SKIP LOCKED), failures, reconciliation."""
from __future__ import annotations

import json
import os
import socket
import traceback
from datetime import timedelta
from typing import Callable

from .db import connection

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


# ───────────── connectors & checkpoints ─────────────
def register_connector(connector: str, source: str, mode: str, description: str = "",
                       freshness_target: timedelta | None = None) -> None:
    with connection() as conn:
        conn.execute("""insert into ingestion.connectors (connector, source, mode, description, freshness_target)
                        values (%s,%s,%s,%s,%s)
                        on conflict (connector) do update set description = excluded.description,
                            mode = excluded.mode, freshness_target = excluded.freshness_target""",
                     (connector, source, mode, description, freshness_target))


def get_checkpoint(connector: str, stream: str = "") -> dict:
    with connection() as conn:
        row = conn.execute("select cursor from ingestion.checkpoints where connector = %s and stream = %s",
                           (connector, stream)).fetchone()
    return row["cursor"] if row else {}


def set_checkpoint(connector: str, stream: str, cursor: dict, last_item_at=None, *, conn=None) -> None:
    """Advance a checkpoint. Pass conn to commit it atomically with the events it covers."""
    sql = """insert into ingestion.checkpoints (connector, stream, cursor, last_item_at, updated_at)
             values (%s,%s,%s,%s, now())
             on conflict (connector, stream) do update set cursor = excluded.cursor,
                 last_item_at = coalesce(excluded.last_item_at, ingestion.checkpoints.last_item_at), updated_at = now()"""
    args = (connector, stream, json.dumps(cursor, default=str), last_item_at)
    if conn is not None:
        conn.execute(sql, args)
    else:
        with connection() as c:
            c.execute(sql, args)


def mark_success(connector: str) -> None:
    with connection() as conn:
        conn.execute("update ingestion.connectors set last_success_at = now() where connector = %s", (connector,))


STALE_FACTOR = 3        # the same rule as health.check: no success for 3 × its freshness target = not synchronised


def freshness(sources, *, conn=None) -> dict[str, dict]:
    """source → {"state": "live" | "stale" | "archived", "synced_at": last success (iso) or None, "reason"} — whether
    what Memory holds of a source is up to date, so a reader never presents old messages as the latest ones. A source's
    connectors are those named after it (`beeper`, `hermes:wild`…), else every connector of that source. stale = its
    last run failed after its last success, or no success for STALE_FACTOR × its freshness target; archived = no
    enabled connector left (the history stays readable)."""
    sources = sorted({s for s in sources if s})
    if not sources:
        return {}
    sql = """select connector, source, enabled, freshness_target, last_success_at, last_error_at, now() as now
             from ingestion.connectors where source = any(%s) and mode in ('push', 'pull', 'import')"""
    if conn is None:
        with connection() as c:
            rows = c.execute(sql, (sources,)).fetchall()
    else:
        rows = conn.execute(sql, (sources,)).fetchall()
    out = {}
    for s in sources:
        mine = [r for r in rows if r["source"] == s]
        named = [r for r in mine if r["connector"] == s or r["connector"].startswith(s + ":")]
        live = [r for r in (named or mine) if r["enabled"]]
        last = max((r["last_success_at"] for r in (named or mine) if r["last_success_at"]), default=None)
        info = {"synced_at": last.isoformat() if last else None}
        if not live:
            out[s] = {"state": "archived", **info, "reason": "no enabled connector"}
            continue
        late = [r for r in live if r["freshness_target"] and (not r["last_success_at"] or
                r["now"] - r["last_success_at"] > STALE_FACTOR * r["freshness_target"])]
        failing = [r for r in live if r["last_error_at"] and (not r["last_success_at"] or
                   r["last_error_at"] > r["last_success_at"])]
        if late or failing:
            out[s] = {"state": "stale", **info,
                      "reason": "last run failed" if failing else f"no successful sync for over {STALE_FACTOR} × its target"}
        else:
            out[s] = {"state": "live", **info}
    return out


def record_failure(connector: str, error: str, *, stream: str = "", item_ref: str = "", details: dict | None = None) -> None:
    with connection() as conn:
        conn.execute("""insert into ingestion.failures (connector, stream, item_ref, error, details) values (%s,%s,%s,%s,%s)""",
                     (connector, stream, item_ref, error[:2000], json.dumps(details or {}, default=str)))
        conn.execute("update ingestion.connectors set last_error = %s, last_error_at = now() where connector = %s",
                     (error[:500], connector))


def resolve_failures(connector: str, stream: str | None = None) -> int:
    """Close open failures once the stream (or the whole connector, stream=None) has synced successfully since."""
    with connection() as conn:
        return len(conn.execute("""update ingestion.failures set resolved_at = now()
                                   where connector = %s and resolved_at is null and (%s::text is null or stream = %s)
                                   returning failure_id""", (connector, stream, stream)).fetchall())


# ───────────── job queue ─────────────
def enqueue(queue: str, payload: dict, *, dedupe_key: str | None = None, priority: int = 100,
            delay: timedelta | None = None, max_attempts: int = 5, conn=None) -> int | None:
    """Add a job; returns its id, or None for a duplicate. Pass conn to commit with canonical events/cursors."""
    if conn is None:
        with connection() as c:
            return enqueue(queue, payload, dedupe_key=dedupe_key, priority=priority, delay=delay,
                           max_attempts=max_attempts, conn=c)
    else:
        row = conn.execute("""insert into ingestion.jobs (queue, payload, dedupe_key, priority, run_after, max_attempts)
                              values (%s,%s,%s,%s, now() + coalesce(%s, interval '0'), %s)
                              on conflict (dedupe_key) do nothing returning job_id""",
                           (queue, json.dumps(payload, default=str), dedupe_key, priority, delay, max_attempts)).fetchone()
    return row["job_id"] if row else None


def claim(queue: str, limit: int = 1) -> list[dict]:
    with connection() as conn:
        return conn.execute("""update ingestion.jobs j set status = 'running', locked_by = %s, locked_at = now(),
                                   attempts = attempts + 1
                               where job_id in (select job_id from ingestion.jobs
                                                where queue = %s and status = 'queued' and run_after <= now()
                                                order by priority, run_after limit %s for update skip locked)
                               returning j.*""", (WORKER_ID, queue, limit)).fetchall()


def complete(job_id: int) -> None:
    with connection() as conn:
        conn.execute("update ingestion.jobs set status = 'done', finished_at = now(), last_error = null where job_id = %s",
                     (job_id,))


def fail(job: dict, error: str) -> None:
    """Retry with exponential backoff; after max_attempts the job is dead (kept for inspection)."""
    dead = job["attempts"] >= job["max_attempts"]
    with connection() as conn:
        conn.execute("""update ingestion.jobs set status = %s, last_error = %s, locked_by = null,
                            run_after = now() + make_interval(secs => least(3600, 30 * power(2, attempts))),
                            finished_at = case when %s then now() end
                        where job_id = %s""", ("dead" if dead else "queued", error[:2000], dead, job["job_id"]))


def requeue_stale(minutes: int = 30, *, queue: str | None = None) -> int:
    """Jobs left 'running' by a crashed worker go back to the queue."""
    with connection() as conn:
        return conn.execute("""update ingestion.jobs set status = 'queued', locked_by = null
                               where status = 'running' and locked_at <= now() - make_interval(mins => %s)
                                 and (%s::text is null or queue = %s)""",
                            (minutes, queue, queue)).rowcount


def work(queue: str, handler: Callable[[dict], None], *, batch: int = 10) -> int:
    """Run up to `batch` ready jobs of a queue through handler(payload). Returns jobs processed."""
    jobs = claim(queue, batch)
    for job in jobs:
        try:
            handler(job["payload"])
            complete(job["job_id"])
        except Exception as e:
            fail(job, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}")
    return len(jobs)


# ───────────── reconciliation ─────────────
def record_reconciliation(connector: str, stream: str, source_count: int, walter_count: int, repaired: int = 0,
                          details: dict | None = None) -> None:
    with connection() as conn:
        conn.execute("""insert into ingestion.reconciliation_runs (connector, stream, finished_at, source_count,
                            walter_count, gaps, repaired, details) values (%s,%s, now(), %s,%s,%s,%s,%s)""",
                     (connector, stream, source_count, walter_count, max(0, source_count - walter_count), repaired,
                      json.dumps(details or {}, default=str)))

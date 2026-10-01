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


def record_failure(connector: str, error: str, *, stream: str = "", item_ref: str = "", details: dict | None = None) -> None:
    with connection() as conn:
        conn.execute("""insert into ingestion.failures (connector, stream, item_ref, error, details) values (%s,%s,%s,%s,%s)""",
                     (connector, stream, item_ref, error[:2000], json.dumps(details or {}, default=str)))
        conn.execute("update ingestion.connectors set last_error = %s, last_error_at = now() where connector = %s",
                     (error[:500], connector))


# ───────────── job queue ─────────────
def enqueue(queue: str, payload: dict, *, dedupe_key: str | None = None, priority: int = 100,
            delay: timedelta | None = None, max_attempts: int = 5) -> int | None:
    """Add a job; returns its id, or None when a job with the same dedupe_key already exists."""
    with connection() as conn:
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


def requeue_stale(minutes: int = 30) -> int:
    """Jobs left 'running' by a crashed worker go back to the queue."""
    with connection() as conn:
        return conn.execute("""update ingestion.jobs set status = 'queued', locked_by = null
                               where status = 'running' and locked_at < now() - make_interval(mins => %s)""",
                            (minutes,)).rowcount


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

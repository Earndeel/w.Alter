"""PostgreSQL access (schema devboard). Writers end with pg_notify('devboard', …) through notify()."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .config import DEFAULT_DSN

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
_conn: psycopg.Connection | None = None


def dsn() -> str:
    return os.environ.get("WALTER_DEVBOARD_DATABASE_URL", DEFAULT_DSN)


def _shared() -> psycopg.Connection:
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg.connect(dsn(), row_factory=dict_row, application_name="walter-devboard")
    return _conn


@contextmanager
def connection():
    """One transaction: commit on success, rollback on error."""
    c = _shared()
    with c.transaction():
        yield c


@contextmanager
def autocommit():
    """A connection of its own for long passes: each `with conn.transaction()` block commits on its own."""
    c = psycopg.connect(dsn(), row_factory=dict_row, autocommit=True, application_name="walter-devboard")
    try:
        yield c
    finally:
        c.close()


def try_lock(conn) -> bool:
    """Session lock of the reading passes (due, backfill, read-session): one at a time, released with the connection."""
    return conn.execute("select pg_try_advisory_lock(hashtext('walter-devboard.reading')) ok").fetchone()["ok"]


def close() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def migrate() -> list[str]:
    applied = []
    with psycopg.connect(dsn(), autocommit=True) as c:
        done = set()
        if c.execute("select to_regclass('devboard.migrations')").fetchone()[0]:
            done = {r[0] for r in c.execute("select version from devboard.migrations")}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.stem not in done:
                c.execute(f.read_text())
                applied.append(f.stem)
    return applied


def notify(conn, what: str, **data) -> None:
    conn.execute("select pg_notify('devboard', %s)", (json.dumps({"what": what, **data}, default=str)[:7000],))

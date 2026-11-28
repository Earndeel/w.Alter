"""Connection handling. Credentials come from ~/.pgpass (never from code or DSNs)."""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# Walter's PostgreSQL address: the variable above, else the host's one declaration (/etc/walter/database.url, no
# password: credentials come from ~/.pgpass), else the default. Renamed hindsight → walter on 2026-11-21.
def _host_dsn() -> str | None:
    try:
        return open(os.environ.get("WALTER_DATABASE_URL_FILE", "/etc/walter/database.url")).read().strip() or None
    except OSError:
        return None


DSN = os.environ.get("WALTER_MEMORY_DATABASE_URL") or _host_dsn() or "postgresql://walter@127.0.0.1:5433/walter"
_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(DSN, min_size=1, max_size=int(os.environ.get("WALTER_MEMORY_POOL_MAX", "8")),
                               kwargs={"row_factory": dict_row, "application_name": "walter-memory"}, open=True)
    return _pool


@contextmanager
def connection():
    """A pooled connection inside a transaction (commit on success, rollback on error)."""
    with pool().connection() as conn:
        with conn.transaction():
            yield conn


def connect() -> psycopg.Connection:
    """A standalone connection (scripts, migrations)."""
    return psycopg.connect(DSN, row_factory=dict_row, application_name="walter-memory")

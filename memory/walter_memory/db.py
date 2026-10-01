"""Connection handling. Credentials come from ~/.pgpass (never from code or DSNs)."""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DSN = os.environ.get("WALTER_MEMORY_DATABASE_URL", "postgresql://hindsight@127.0.0.1:5433/hindsight")
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

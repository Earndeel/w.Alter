"""Connection handling. Credentials come from ~/.pgpass (never from code or DSNs)."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get("WALTER_ROUTER_DATABASE_URL", "postgresql://hindsight@127.0.0.1:5433/hindsight")
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def connect() -> psycopg.Connection:
    return psycopg.connect(DSN, row_factory=dict_row, application_name="walter-router")


def migrate() -> list[str]:
    """Apply every migrations/NNN_*.sql not yet recorded in models.schema_migrations (each file is one transaction)."""
    applied: list[str] = []
    with connect() as conn:
        conn.autocommit = True
        exists = conn.execute("select to_regclass('models.schema_migrations') as t").fetchone()["t"]
        done = {r["version"] for r in conn.execute("select version from models.schema_migrations")} if exists else set()
        for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")):
            if path.stem not in done:
                conn.execute(path.read_text())
                applied.append(path.stem)
    return applied

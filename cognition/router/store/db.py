"""Connection handling. Credentials come from ~/.pgpass (never from code or DSNs)."""
from __future__ import annotations

from walter_router import paths
import os

import psycopg
from psycopg.rows import dict_row

# Walter's PostgreSQL address: the variable above, else the host's one declaration (/etc/walter/database.url, no
# password: credentials come from ~/.pgpass), else the default. Renamed hindsight → walter on 2026-11-21.
def _host_dsn() -> str | None:
    try:
        return open(os.environ.get("WALTER_DATABASE_URL_FILE", "/etc/walter/database.url")).read().strip() or None
    except OSError:
        return None


DSN = os.environ.get("WALTER_ROUTER_DATABASE_URL") or _host_dsn() or "postgresql://walter@127.0.0.1:5433/walter"
MIGRATIONS = paths.MIGRATIONS


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
                # recorded here too: a migration that forgets its own insert must not run again (022/023 did)
                conn.execute("insert into models.schema_migrations (version) values (%s) on conflict do nothing",
                             (path.stem,))
                applied.append(path.stem)
    return applied

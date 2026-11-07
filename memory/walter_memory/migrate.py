"""walter-memory migrate: apply this module's migrations in order and record them (2026-10-29, Walter Clean).

Before this runner the migrations were applied by hand with psql; a blank database could not be built from them
(fixed the same day: 000_extensions, 001 on a blank database, 004b kardex base). Like psql, each file runs statement by
statement in autocommit: a file that opens its own transaction (begin; ... commit;) is atomic, and statements that
cannot run in a transaction (create index concurrently) work. Each file is recorded in core.schema_migrations with
its sha256 once it has run. `--baseline-through FILE` records the files up to FILE as already applied without running them: the
first instance's database got them by hand. A recorded file whose content changed afterwards is reported, never
re-run (fix forward with a new migration).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .db import connect

DIR = Path(__file__).resolve().parent.parent / "migrations"


import re

_DOLLAR = re.compile(r"\$([A-Za-z_][A-Za-z_0-9]*)?\$")


def statements(sql: str) -> list[str]:
    """Split a SQL script at top-level semicolons, as psql does: comments, quoted strings and identifiers and
    dollar-quoted bodies ($$ … $$, $tag$ … $tag$) are never split."""
    out, buf, i, n = [], [], 0, len(sql)
    while i < n:
        c = sql[i]
        if sql.startswith("--", i):
            j = sql.find("\n", i); j = n if j < 0 else j
            buf.append(sql[i:j]); i = j
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2); j = n if j < 0 else j + 2
            buf.append(sql[i:j]); i = j
        elif c in ("'", '"'):
            j = i + 1
            while j < n:
                if sql[j] == c and j + 1 < n and sql[j + 1] == c:
                    j += 2; continue
                if sql[j] == c:
                    break
                j += 1
            buf.append(sql[i:j + 1]); i = j + 1
        elif c == "$" and (m := _DOLLAR.match(sql, i)):
            tag = m.group(0)
            j = sql.find(tag, m.end()); j = n if j < 0 else j + len(tag)
            buf.append(sql[i:j]); i = j
        elif c == ";":
            stmt = "".join(buf).strip()
            if stmt and not all(l.strip().startswith("--") or not l.strip() for l in stmt.splitlines()):
                out.append(stmt)
            buf, i = [], i + 1
        else:
            buf.append(c); i += 1
    stmt = "".join(buf).strip()
    if stmt and not all(l.strip().startswith("--") or not l.strip() for l in stmt.splitlines()):
        out.append(stmt)
    return out


def _run_file(conn, p: Path) -> None:
    try:
        for stmt in statements(p.read_text()):
            conn.execute(stmt)
    except Exception:
        conn.execute("rollback")              # a file's own open transaction must not stay open; harmless otherwise
        raise


def files() -> list[Path]:
    return sorted(p for p in DIR.glob("*.sql") if p.is_file())


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def recorded(conn) -> dict[str, dict]:
    if not conn.execute("select to_regclass('core.schema_migrations') t").fetchone()["t"]:
        return {}
    return {r["version"]: r for r in conn.execute("select version, sha256, mode, applied_at from core.schema_migrations")}


def status() -> dict:
    with connect() as conn:
        done = recorded(conn)
    rows = [{"file": p.name, "recorded": done.get(p.name, {}).get("mode"),
             "changed_since": bool(p.name in done and done[p.name]["sha256"] != _sha(p))} for p in files()]
    return {"files": rows, "pending": [r["file"] for r in rows if not r["recorded"]],
            "changed_since_recorded": [r["file"] for r in rows if r["changed_since"]]}


def migrate(*, baseline_through: str | None = None, dry_run: bool = False) -> dict:
    out = {"applied": [], "baseline": [], "dry_run": dry_run}
    with connect() as conn:
        conn.autocommit = True
        done = recorded(conn)
        for p in files():
            if p.name in done:
                continue
            mode = "baseline" if baseline_through and p.name <= baseline_through else "applied"
            out[mode].append(p.name)
            if dry_run:
                continue
            if mode == "applied":
                _run_file(conn, p)
            if not recorded(conn) and p.name != "019_schema_migrations.sql":
                conn.execute("create schema if not exists core")                 # the journal itself, first of all
                conn.execute((DIR / "019_schema_migrations.sql").read_text())
            conn.execute("insert into core.schema_migrations (version, sha256, mode) values (%s, %s, %s) "
                         "on conflict (version) do nothing", (p.name, _sha(p), mode))
            done = recorded(conn)
    return out


def accept_change(name: str) -> dict:
    """Record the new content of a 'baseline' file (never run on this database: its old and new content are history
    only). An 'applied' file is refused: a change to what ran must be a new migration."""
    p = DIR / name
    with connect() as conn:
        row = recorded(conn).get(name)
        if not row:
            return {"error": f"{name} is not recorded"}
        if row["mode"] != "baseline":
            return {"error": f"{name} ran on this database: fix forward with a new migration"}
        conn.execute("update core.schema_migrations set sha256 = %s where version = %s", (_sha(p), name))
    return {"accepted": name, "previous_sha256": row["sha256"], "sha256": _sha(p)}

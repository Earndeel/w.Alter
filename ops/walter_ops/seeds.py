"""Walter Clean, reference data (addendum 2026-10-29, C.3 step 3): export, load, prove.

export(dest)        the reference rows of every declared table (contracts/data-classes.json, minus instance_rows),
                    as CSV with header, zstd-compressed, plus a manifest (rows, sha256, columns). A release artifact,
                    not a git file. Exported from the live database through `docker exec` (no row is printed).
clean_db_check()    builds a database as Walter Clean would: the modules' migrations on a disposable PostgreSQL
                    without network, then the exported reference rows; then proves it: every reference table holds
                    exactly the exported rows, and no row of any table of any schema contains a private marker of the
                    instance (counts only). Rows the migrations write themselves (software defaults: system connectors,
                    default budgets, task definitions) are allowed and reported; they must name nobody.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from walter_backup import core as backup

from . import clean, data


def _live(args: list[str], **kw) -> subprocess.CompletedProcess:
    pg = backup.config().get("pg") or {}
    return subprocess.run(["docker", "exec", *kw.pop("docker", []), pg["container"], "psql", "-U", pg["user"], "-d",
                           pg["database"], "-v", "ON_ERROR_STOP=1", *args], capture_output=True, **kw)


def export(dest: Path) -> dict:
    dest.mkdir(parents=True, exist_ok=False)
    manifest = {"version": 1, "tables": {}}
    for table, spec in sorted(data.declarations().items()):
        if spec["class"] != "reference":
            continue
        where = data.shipped_where(spec)
        r = _live(["-c", f"copy (select * from {table} where {where}) to stdout with (format csv, header true)"],
                  timeout=1800)
        if r.returncode:
            raise RuntimeError(f"export {table}: " + r.stderr.decode()[-300:])
        raw = r.stdout
        rows = max(raw.count(b"\n") - 1, 0) if b'"' not in raw else None      # exact count below
        n = int(_live(["-Atc", f"select count(*) from {table} where {where}"], text=True).stdout.strip())
        out = dest / f"{table}.csv.zst"
        z = subprocess.run(["zstd", "-q", "-19", "-T2", "-o", str(out)], input=raw, capture_output=True)
        if z.returncode:
            raise RuntimeError("zstd: " + z.stderr.decode()[-200:])
        manifest["tables"][table] = {"module": spec["module"], "rows": n, "bytes": len(raw),
                                     "sha256": hashlib.sha256(raw).hexdigest(),
                                     "columns": raw.split(b"\n", 1)[0].decode()}
        del rows
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def _disposable(name: str, db: str, image: str) -> None:
    r = subprocess.run(["docker", "run", "-d", "--rm", "--name", name, "--network", "none", "-e",
                        "POSTGRES_PASSWORD=" + uuid.uuid4().hex, "-e", "POSTGRES_DB=" + db, image],
                       capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise RuntimeError("cannot start the disposable database: " + r.stderr.strip()[-200:])
    for _ in range(90):
        ok = subprocess.run(["docker", "exec", name, "psql", "-U", "postgres", "-d", db, "-Atc", "select 1"],
                            capture_output=True, timeout=10).returncode == 0
        if ok:
            time.sleep(2)
            if subprocess.run(["docker", "exec", name, "psql", "-U", "postgres", "-d", db, "-Atc", "select 1"],
                              capture_output=True, timeout=10).returncode == 0:
                return
        time.sleep(1)
    raise RuntimeError("the disposable database did not start")


def _psql(name: str, db: str, sql: str, *, input: bytes | None = None) -> str:
    r = subprocess.run(["docker", "exec", "-i", name, "psql", "-U", "postgres", "-d", db, "-v", "ON_ERROR_STOP=1",
                        "-Atc", sql], input=input, capture_output=True, timeout=1800)
    if r.returncode:
        raise RuntimeError(r.stderr.decode()[-400:])
    return r.stdout.decode()


def clean_db_check(*, seeds: Path | None = None, keep_seeds: Path | None = None) -> dict:
    cfg = clean.config()
    db, image = cfg["postgres"]["database"], cfg["postgres"]["image"]
    name = f"walter-clean-{uuid.uuid4().hex[:8]}"
    work = Path(tempfile.mkdtemp(prefix="walter-clean-seeds-", dir="/var/tmp"))
    report = {"ok": False, "container": name}
    try:
        seed_dir = seeds or (keep_seeds or work / "seeds")
        manifest = json.loads((seed_dir / "manifest.json").read_text()) if seeds else export(seed_dir)
        report["seed_tables"] = len(manifest["tables"])
        _disposable(name, db, image)
        applied = 0
        for mset in cfg["migrations"]:
            for f in sorted(clean.module_dir(mset["module"], mset["dir"]).glob("*.sql")):
                r = subprocess.run(["docker", "exec", "-i", name, "psql", "-U", "postgres", "-d", db, "-q", "-v",
                                    "ON_ERROR_STOP=1", "-f", "-"], input=f.read_bytes(), capture_output=True, timeout=600)
                if r.returncode:
                    report["error"] = f"migration {mset['module']}/{f.name} failed"
                    return report
                applied += 1
        report["migrations_applied"] = applied
        decl = data.declarations()
        tables = sorted(data.live_tables(cfg["compare"]["schemas"]))
        count = lambda t: int(_psql(name, db, f"select count(*) from {t}").strip())          # noqa: E731
        after_migrations = {t: count(t) for t in tables}
        loaded = {}
        for table, meta in manifest["tables"].items():
            raw = subprocess.run(["zstd", "-q", "-d", "-c", str(seed_dir / f"{table}.csv.zst")], capture_output=True,
                                 check=True).stdout
            if hashlib.sha256(raw).hexdigest() != meta["sha256"]:
                report["error"] = f"seed {table} does not match its manifest"
                return report
            cols = meta["columns"]
            # rows written by the migrations themselves (task definitions, source registry…) are replaced by the
            # exported current rows; foreign keys are not checked during the load, then every table is verified
            _psql(name, db, f"set session_replication_role = replica; delete from {table}; "
                            f"copy {table} ({cols}) from stdin with (format csv, header true)", input=raw)
            loaded[table] = {"expected": meta["rows"], "loaded": count(table)}
        _psql(name, db, """do $$ declare r record; begin
            for r in select pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname) seq,
                            format('%I.%I', n.nspname, c.relname) tbl, a.attname col
                     from pg_attribute a join pg_class c on c.oid = a.attrelid join pg_namespace n on n.oid = c.relnamespace
                     where a.attnum > 0 and not a.attisdropped and c.relkind = 'r'
                       and pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname) is not null loop
              execute format('select setval(%L, coalesce((select max(%I) from %s), 0) + 1, false)', r.seq, r.col, r.tbl);
            end loop; end $$""")
        mismatched = sorted(t for t, v in loaded.items() if v["expected"] != v["loaded"])
        others = {t: after_migrations[t] for t in tables if t not in loaded and after_migrations[t]}
        rx = data.pattern(data.markers())
        all_tables = _psql(name, db, "select n.nspname || '.' || c.relname from pg_class c join pg_namespace n on "
                                     "n.oid = c.relnamespace where c.relkind in ('r', 'p') and n.nspname not in "
                                     "('pg_catalog', 'information_schema')").split()
        leaks = {}
        for t in all_tables:
            n = int(_psql(name, db, f"select count(*) from {t} x where x::text ~* $m${rx}$m$").strip())
            if n:
                leaks[t] = n
        report.update(tables_scanned=len(all_tables), markers_checked=len(data.markers()),
                      reference_loaded=loaded, mismatched=mismatched,
                      rows_written_by_migrations_outside_reference=others,
                      rows_with_private_markers=leaks,
                      ok=bool(rx) and not mismatched and not leaks)
        return report
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=60)
        if not keep_seeds:
            shutil.rmtree(work, ignore_errors=True)

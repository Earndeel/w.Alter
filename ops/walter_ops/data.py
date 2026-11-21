"""Walter Clean, data part (addendum 2026-10-29, C.2/C.5): what each table is, and what a clean install may carry.

Each module declares its tables in contracts/data-classes.json: reference (shipped with Walter Clean, minus the rows
matching instance_rows), instance (the person's data), runtime (recomputed by the module), legacy. `check()` reads the
live database's catalogue and fails on any table nobody classified or any declaration of a table that does not exist,
then counts the reference rows a clean install would carry and searches them for the instance's private markers
(instance.toml [privacy].markers, the owner's e-mails and form of address). No value is ever reported: only counts.
"""
from __future__ import annotations

import json
import re
import subprocess
import tomllib

from walter_backup import core as backup

from . import clean

CLASSES = ("reference", "instance", "runtime", "legacy")


def declarations() -> dict[str, dict]:
    out = {}
    for d in clean.config().get("data", []):
        path = clean.module_dir(d["module"], d.get("file", "contracts/data-classes.json"))
        doc = json.loads(path.read_text())
        for table, spec in doc["tables"].items():
            if spec.get("class") not in CLASSES:
                raise ValueError(f"{d['module']}: {table} has class {spec.get('class')!r}")
            out[table] = {**spec, "module": d["module"]}
    return out


def markers() -> list[str]:
    """The instance's private markers: never printed, only matched."""
    try:
        inst = tomllib.loads((backup.instance_root() / "instance.toml").read_text())
    except (OSError, ValueError):
        return []
    owner = inst.get("owner") or {}
    found = list((inst.get("privacy") or {}).get("markers") or []) + list(owner.get("emails") or [])
    if owner.get("address"):
        found.append(owner["address"])
    return sorted({m for m in found if isinstance(m, str) and len(m) >= 3})


def _psql(sql: str) -> list[str]:
    pg = backup.config().get("pg") or {}
    r = subprocess.run(["docker", "exec", pg["container"], "psql", "-U", pg["user"], "-d", pg["database"], "-v",
                        "ON_ERROR_STOP=1", "-Atc", sql], capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise RuntimeError("psql: " + r.stderr.strip()[-300:])
    return [l for l in r.stdout.splitlines() if l]


def pattern(words: list[str]) -> str:
    return "|".join(re.escape(w) for w in words)


def live_tables(schemas: list[str]) -> set[str]:
    rows = _psql("select n.nspname || '.' || c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                 "where c.relkind in ('r', 'p') and not c.relispartition and n.nspname = any(array[%s])"
                 % ",".join("'%s'" % s.replace("'", "") for s in schemas))
    return set(rows)


def shipped_where(spec: dict) -> str:
    return f"not coalesce(({spec['instance_rows']}), false)" if spec.get("instance_rows") else "true"


def check() -> dict:
    cfg = clean.config()
    decl = declarations()
    live = live_tables(cfg["compare"]["schemas"])
    unclassified = sorted(live - set(decl))
    stale = sorted(set(decl) - live)
    words = markers()
    rx = pattern(words)
    reference = {}
    for table, spec in sorted(decl.items()):
        if spec["class"] != "reference" or table not in live:
            continue
        where = shipped_where(spec)
        total, shipped = _psql(f"select count(*), count(*) filter (where {where}) from {table}")[0].split("|")
        hits = int(_psql(f"select count(*) from {table} t where {where} and t::text ~* $m${rx}$m$")[0]) if rx else None
        reference[table] = {"rows": int(total), "shipped": int(shipped), "rows_with_private_markers": hits}
    counts = {c: sum(1 for s in decl.values() if s["class"] == c) for c in CLASSES}
    leaking = sorted(t for t, r in reference.items() if r["rows_with_private_markers"])
    return {"ok": not unclassified and not stale and not leaking and bool(words),
            "tables": len(live), "classes": counts, "unclassified": unclassified, "stale_declarations": stale,
            "markers_checked": len(words), "reference": reference, "leaking_reference_tables": leaking}

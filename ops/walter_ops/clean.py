"""Walter Clean, PostgreSQL part (addendum 2026-10-29, C.3): can the modules' own migrations build the database?

`migrations_check()` starts a disposable PostgreSQL (same image as the live one, no network, no volume), applies every
declared migration set in order through psql, then compares the resulting structure with the live database's
structure (pg_dump --schema-only of the software schemas; no row is read). Differences are reported per object:
  missing      in the live database, not produced by the migrations (the migrations are incomplete)
  extra        produced by the migrations, absent from the live database
  different    same object, different definition
  order_only   same lines in another order (column added by ALTER in one history, by CREATE in the other): reported,
               not failing
Run-time objects (monthly partitions) are declared in config/clean.toml and left out. The container is always removed.
Standard library only; the live database is reached through `docker exec` on the container named by the backup
configuration ([pg] container/database/user).
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
import time
import tomllib
import uuid
from pathlib import Path

from walter_backup import core as backup

MODULE = Path(__file__).resolve().parent.parent
HEADER = re.compile(r"^-- Name: (?P<name>.+?); Type: (?P<type>[A-Z ]+?); Schema: (?P<schema>[^;]+);[^\n]*$", re.M)


def config() -> dict:
    cfg = tomllib.loads((MODULE / "config" / "clean.toml").read_text())
    inst = backup.instance_root() / "config" / "ops" / "clean.toml"
    if inst.is_file():
        for k, v in tomllib.loads(inst.read_text()).items():
            cfg[k] = {**cfg[k], **v} if isinstance(v, dict) and isinstance(cfg.get(k), dict) else v
    return cfg


def _run(*cmd, input=None, timeout=600) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, input=input, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 124, "", str(exc))


def module_dir(module: str, sub: str) -> Path:
    r = _run("walter", "path", module, sub, timeout=30)
    if r.returncode or not r.stdout.strip():
        raise RuntimeError(f"walter path {module} {sub}: {r.stderr.strip()[:200]}")
    return Path(r.stdout.strip())


def objects(dump: str) -> dict[str, str]:
    """pg_dump --schema-only text -> {"TYPE schema.name": normalised definition}."""
    out, marks = {}, list(HEADER.finditer(dump))
    for i, m in enumerate(marks):
        body = dump[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(dump)]
        lines = [l.rstrip() for l in body.splitlines()
                 if l.strip() and not l.startswith("--") and not l.startswith("\\") and not l.startswith("SET ") and not l.startswith("SELECT pg_catalog.")]
        key = f"{m['type']} {m['schema']}.{m['name']}"
        n, k = 2, key
        while k in out:                      # same name, same type (overloaded functions): keep each
            k, n = f"{key} #{n}", n + 1
        out[k] = "\n".join(lines).strip()
    return out


def _dump(container: str, user: str, db: str, schemas: list[str]) -> str:
    args = ["docker", "exec", container, "pg_dump", "-U", user, "-d", db, "--schema-only", "--no-owner",
            "--no-privileges", "--no-comments"]
    for s in schemas:
        args += ["-n", s]
    r = _run(*args, timeout=300)
    if r.returncode:
        raise RuntimeError("pg_dump failed: " + r.stderr.strip()[-300:])
    return r.stdout


def compare(live: dict[str, str], built: dict[str, str], runtime: list[str]) -> dict:
    skip = lambda k: any(fnmatch.fnmatchcase(k.split(" #")[0], p) for p in runtime)   # noqa: E731
    live = {k: v for k, v in live.items() if not skip(k)}
    built = {k: v for k, v in built.items() if not skip(k)}
    canon = lambda s: sorted(l.strip().rstrip(",") for l in s.splitlines())         # noqa: E731
    both = [k for k in set(live) & set(built) if live[k] != built[k]]
    return {"missing": sorted(set(live) - set(built)), "extra": sorted(set(built) - set(live)),
            "different": sorted(k for k in both if canon(live[k]) != canon(built[k])),
            # same columns/lines in another order (a column added by ALTER in one history, by CREATE in the other):
            # equivalent for code that names its columns; reported, not failing
            "order_only": sorted(k for k in both if canon(live[k]) == canon(built[k]))}


def migrations_check(*, keep_dumps: Path | None = None) -> dict:
    cfg, bcfg = config(), backup.config()
    pg = bcfg.get("pg") or {}
    name = f"walter-clean-{uuid.uuid4().hex[:8]}"
    image, db = cfg["postgres"]["image"], cfg["postgres"]["database"]
    report = {"image": image, "container": name, "sets": [], "ok": False}
    r = _run("docker", "run", "-d", "--rm", "--name", name, "--network", "none", "-e", "POSTGRES_PASSWORD=" + uuid.uuid4().hex,
             "-e", "POSTGRES_DB=" + db, image, timeout=120)
    if r.returncode:
        report["error"] = "cannot start the disposable database: " + r.stderr.strip()[-200:]
        return report
    try:
        for _ in range(60):
            if _run("docker", "exec", name, "pg_isready", "-U", "postgres", "-d", db, timeout=10).returncode == 0:
                break
            time.sleep(1)
        time.sleep(2)                                   # the image restarts postgres once after initdb
        for _ in range(30):
            if _run("docker", "exec", name, "psql", "-U", "postgres", "-d", db, "-Atc", "select 1", timeout=10).returncode == 0:
                break
            time.sleep(1)
        failed = False
        for mset in cfg["migrations"]:
            d = module_dir(mset["module"], mset["dir"])
            files = sorted(p for p in d.glob("*.sql") if p.is_file())
            res = {"module": mset["module"], "files": len(files), "applied": 0, "failed": None}
            for f in files:
                out = _run("docker", "exec", "-i", name, "psql", "-U", "postgres", "-d", db, "-q", "-v", "ON_ERROR_STOP=1",
                           "-f", "-", input=f.read_text(), timeout=600)
                if out.returncode:
                    err = next((l for l in out.stderr.splitlines() if "ERROR" in l), out.stderr.strip()[-300:])
                    res["failed"] = {"file": f.name, "error": err[:400]}
                    failed = True
                    break
                res["applied"] += 1
            report["sets"].append(res)
            if failed:
                break
        if failed:
            report["error"] = "a migration failed on a blank database"
            return report
        schemas = cfg["compare"]["schemas"]
        built_dump = _dump(name, "postgres", db, schemas)
        live_dump = _dump(pg["container"], pg["user"], pg["database"], schemas)
        if keep_dumps:
            keep_dumps.mkdir(parents=True, exist_ok=True)
            (keep_dumps / "built.sql").write_text(built_dump)
            (keep_dumps / "live.sql").write_text(live_dump)
        diff = compare(objects(live_dump), objects(built_dump), cfg["compare"].get("runtime_objects", []))
        report.update(diff=diff, counts={k: len(v) for k, v in diff.items()})
        report["ok"] = not (diff["missing"] or diff["extra"] or diff["different"])
        return report
    finally:
        _run("docker", "rm", "-f", name, timeout=60)

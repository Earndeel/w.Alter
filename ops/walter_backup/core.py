"""walter-backup — one façade over Walter's existing backup, restore and versioning mechanisms (P5, 2026-10-28).

Decisions (owner, 2026-10-27/28): start with a façade that reuses what exists; move implementations only after
qualification, keeping compatibility. Backup must keep working when Router, Context, Memory (partly), Hermes, DSH or
every model provider is down: this package uses the Python standard library, systemd, git, docker and files only.

Three separate questions (never merged into one "ok"):
  conformity      does the code match its contracts (`walter contracts check`)
  backup_health   did each backup kind run recently and successfully, where is its newest output
  restorability   when was a restore last proven (offsite restore test, isolated drill), can a drill run now
"""
from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

MODULE = Path(__file__).resolve().parent.parent
INCIDENT_VERSION = 1


def sh(*cmd: str, timeout: float = 60, input: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 124, "", str(exc))


def instance_root() -> Path:
    root = os.environ.get("WALTER_INSTANCE")
    if not root:
        try:
            root = Path("/etc/walter/instance").read_text().strip()
        except OSError:
            root = ""
    return Path(root) if root else MODULE


def config() -> dict:
    """Module defaults, then the instance's overrides (deep merge on tables)."""
    def merge(a: dict, b: dict) -> dict:
        out = dict(a)
        for k, v in b.items():
            out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
        return out
    cfg = tomllib.loads((MODULE / "config" / "backup.toml").read_text())
    inst = instance_root() / "config" / "backup" / "backup.toml"
    if inst.exists():
        cfg = merge(cfg, tomllib.loads(inst.read_text()))
    return cfg


def state_dir() -> Path:
    d = instance_root() / "state" / "backup"
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def _age_h(ts: float | None) -> float | None:
    return round((time.time() - ts) / 3600, 1) if ts else None


def unit_last(unit: str) -> dict:
    """Last run of a systemd unit: result, end time, and the last time it succeeded (journal)."""
    r = sh("systemctl", "show", f"{unit}.service", "-p", "Result", "-p", "ExecMainExitTimestamp",
           "-p", "ExecMainStatus", "-p", "ActiveState")
    props = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    end = props.get("ExecMainExitTimestamp") or ""
    ts = None
    if end and end != "n/a":
        p = sh("date", "-d", end, "+%s")
        ts = float(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip() else None
    ok_line = sh("journalctl", "-u", f"{unit}.service", "--since", "-62 days", "--no-pager", "-o", "short-unix",
                 "--grep", "Deactivated successfully|Finished", "-n", "1", timeout=30).stdout.strip().splitlines()
    last_ok = float(ok_line[-1].split()[0]) if ok_line and ok_line[-1].split()[0].replace(".", "").isdigit() else None
    if last_ok is None and props.get("Result") == "success" and ts:      # journal rotated: the last run did succeed
        last_ok = ts
    return {"unit": unit, "result": props.get("Result"), "state": props.get("ActiveState"),
            "exit_status": props.get("ExecMainStatus"), "ended_age_h": _age_h(ts), "last_success_age_h": _age_h(last_ok)}


def newest(directory: str, pattern: str) -> dict | None:
    d = Path(directory)
    files = [p for p in d.iterdir() if fnmatch.fnmatch(p.name, pattern)] if d.is_dir() else []
    if not files:
        return None
    p = max(files, key=lambda x: x.stat().st_mtime)
    return {"file": p.name, "bytes": p.stat().st_size, "age_h": _age_h(p.stat().st_mtime), "count": len(files)}


def conformity() -> dict:
    r = sh("walter", "contracts", "check", timeout=120)
    try:
        d = json.loads(r.stdout)
        return {"ok": bool(d.get("ok")), "registry_matches_contracts": d.get("registry_matches_contracts")}
    except ValueError:
        return {"ok": None, "error": "walter contracts check unavailable"}


def backup_health(cfg: dict) -> dict:
    out = {}
    for kind, k in (cfg.get("kinds") or {}).items():
        if kind.startswith("restore"):
            continue
        item = {"unit": unit_last(k["unit"])} if k.get("unit") else {}
        if k.get("dir"):
            item["newest"] = newest(k["dir"], k.get("pattern", "*"))
        age = (item.get("newest") or {}).get("age_h") if k.get("dir") else item.get("unit", {}).get("last_success_age_h")
        item["age_h"], item["max_age_hours"] = age, k.get("max_age_hours")
        item["ok"] = age is not None and age <= float(k.get("max_age_hours", 26)) and \
            item.get("unit", {}).get("result") in (None, "success")
        out[kind] = item
    return out


def restorability(cfg: dict) -> dict:
    out = {}
    kinds = cfg.get("kinds") or {}
    if "restore_test" in kinds:
        u = unit_last(kinds["restore_test"]["unit"])
        out["offsite_restore_test"] = {**u, "ok": u["result"] == "success" and (u["last_success_age_h"] or 1e9)
                                       <= kinds["restore_test"].get("max_age_hours", 840)}
    if "restore_drill" in kinds:
        k = kinds["restore_drill"]
        rep = Path(k.get("report", ""))
        try:
            d = json.loads(rep.read_text())
            age = _age_h(rep.stat().st_mtime)
            out["isolated_drill"] = {"ok": bool(d.get("ok")) and age <= k.get("max_age_hours", 1440), "report_ok": d.get("ok"),
                                     "age_h": age}
        except (OSError, ValueError):
            out["isolated_drill"] = {"ok": False, "error": "no drill report"}
    free = shutil.disk_usage("/").free / 2**30
    need = float((cfg.get("restore") or {}).get("min_free_gib_drill", 16))
    out["disk"] = {"free_gib": round(free, 1), "needed_for_drill_gib": need, "drill_possible_now": free >= need}
    return out


def status() -> dict:
    cfg = config()
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "conformity": conformity(),
            "backup_health": backup_health(cfg), "restorability": restorability(cfg)}


# ---- versioning (Git Manager) ----------------------------------------------------------------------------------

def repos(cfg: dict | None = None) -> list[Path]:
    cfg = cfg or config()
    roots = []
    r = sh("walter", "modules", timeout=60)
    try:
        roots = [m["root"] for m in json.loads(r.stdout).get("modules", [])]
    except ValueError:
        pass
    roots += [str(MODULE)] + list((cfg.get("git") or {}).get("extra_repos") or [])
    tops = []
    for root in roots:
        top = sh("git", "-C", root, "rev-parse", "--show-toplevel").stdout.strip()
        if top and Path(top) not in tops:
            tops.append(Path(top))
    return tops


def repo_state(repo: Path) -> dict:
    g = lambda *a: sh("git", "-C", str(repo), *a, timeout=60).stdout
    porcelain = [l for l in g("status", "--porcelain").splitlines() if l]
    oldest = None
    for line in porcelain:
        p = repo / line[3:].split(" -> ")[-1].strip('"')
        try:
            m = p.stat().st_mtime
            oldest = m if oldest is None else min(oldest, m)
        except OSError:
            pass
    head = g("log", "-1", "--format=%H %ct").split()
    return {"repo": str(repo), "branch": g("rev-parse", "--abbrev-ref", "HEAD").strip(),
            "head": head[0][:12] if head else None, "head_age_h": _age_h(float(head[1])) if len(head) > 1 else None,
            "dirty": len([l for l in porcelain if not l.startswith("??")]),
            "untracked": len([l for l in porcelain if l.startswith("??")]),
            "oldest_change_age_h": _age_h(oldest), "remotes": [r for r in g("remote").split() if r],
            "checkpoints": len([l for l in g("for-each-ref", "refs/walter-backup/").splitlines() if l])}


def git_inventory() -> list[dict]:
    return [repo_state(r) for r in repos()]


# ---- checkpoints (adapted to the risk) --------------------------------------------------------------------------

def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def checkpoint(level: str, scope: str, *, schemas: list[str] | None = None, note: str = "") -> dict:
    """git: a ref on the repository's exact working state (tracked files, uncommitted included; HEAD and index
    untouched) — cheap, for a recipe or code change. files: an archive of the module's directory. db: a pg_dump of
    the named schemas — for a migration. Each records a line in state/backup/checkpoints.jsonl."""
    cfg, stamp = config(), _stamp()
    rec = {"at": stamp, "level": level, "scope": scope, "note": note}
    if level == "git":
        top = sh("git", "-C", scope, "rev-parse", "--show-toplevel").stdout.strip()
        if not top:
            raise ValueError(f"not a git repository: {scope}")
        commit = sh("git", "-C", top, "stash", "create", f"walter-backup checkpoint {stamp}").stdout.strip() or \
            sh("git", "-C", top, "rev-parse", "HEAD").stdout.strip()
        ref = f"refs/walter-backup/checkpoints/{stamp}"
        if sh("git", "-C", top, "update-ref", ref, commit).returncode:
            raise RuntimeError("git update-ref failed")
        untracked = [l[3:] for l in sh("git", "-C", top, "status", "--porcelain").stdout.splitlines() if l.startswith("??")]
        rec.update(repo=top, ref=ref, commit=commit, untracked_not_included=untracked[:50],
                   restore=f"git -C {top} stash apply {commit}   # or: git -C {top} checkout {commit} -- <path>")
    elif level == "files":
        dest = Path(cfg.get("checkpoints", {}).get("dir") or state_dir() / "checkpoints")
        dest.mkdir(parents=True, exist_ok=True, mode=0o700)
        out = dest / f"{Path(scope).name}-{stamp}.tar.zst"
        r = sh("tar", "--zstd", "-cf", str(out), "--exclude=venv", "--exclude=.venv", "--exclude=node_modules",
               "--exclude=__pycache__", "-C", str(Path(scope).parent), Path(scope).name, timeout=1800)
        if r.returncode:
            raise RuntimeError("tar failed: " + r.stderr[-200:])
        os.chmod(out, 0o600)
        rec.update(file=str(out), bytes=out.stat().st_size,
                   restore=f"tar --zstd -xf {out} -C <empty dir>   # compare, then copy back what is needed")
    elif level == "db":
        if not schemas:
            raise ValueError("db checkpoint needs --schema (one or more)")
        pg = cfg.get("pg") or {}
        dest = Path(cfg.get("checkpoints", {}).get("dir") or state_dir() / "checkpoints")
        dest.mkdir(parents=True, exist_ok=True, mode=0o700)
        out = dest / f"pg-{'+'.join(schemas)}-{stamp}.dump"
        user = _pg_user()
        args = ["docker", "exec", pg.get("container", "hindsight-pg"), "pg_dump", "-U", user, "-d",
                pg.get("database", "hindsight"), "-Fc"] + [x for s in schemas for x in ("-n", s)]
        with open(out, "wb") as f:
            p = subprocess.run(args, stdout=f, stderr=subprocess.PIPE, timeout=3600)
        if p.returncode:
            out.unlink(missing_ok=True)
            raise RuntimeError("pg_dump failed: " + p.stderr.decode()[-200:])
        os.chmod(out, 0o600)
        rec.update(file=str(out), bytes=out.stat().st_size, schemas=schemas,
                   restore=f"pg_restore --clean --if-exists -n <schema> {out}   # only with the owner's go-ahead")
    else:
        raise ValueError("level must be git, files or db")
    with open(state_dir() / "checkpoints.jsonl", "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _pg_user() -> str:
    try:
        return Path("/root/.pgpass").read_text().splitlines()[0].split(":")[3]
    except (OSError, IndexError):
        return "hindsight"


def checkpoints(limit: int = 20) -> list[dict]:
    p = state_dir() / "checkpoints.jsonl"
    lines = p.read_text().splitlines() if p.exists() else []
    return [json.loads(l) for l in lines[-limit:]]


# ---- verification -------------------------------------------------------------------------------------------------

def verify(sample: int | None = None) -> dict:
    """Cheap proofs on the newest local copies; the full offsite restore stays the monthly unit."""
    cfg = config()
    out = {}
    k = (cfg.get("kinds") or {})
    if "pg" in k and (n := newest(k["pg"]["dir"], k["pg"].get("pattern", "*"))):
        path = Path(k["pg"]["dir"]) / n["file"]
        with open(path, "rb") as f:
            p = subprocess.run(["docker", "exec", "-i", (cfg.get("pg") or {}).get("container", "hindsight-pg"),
                                "pg_restore", "--list"], stdin=f, capture_output=True, timeout=600)
        out["pg_dump_readable"] = {"file": n["file"], "ok": p.returncode == 0,
                                   "entries": len([l for l in p.stdout.decode(errors="replace").splitlines()
                                                   if l and not l.startswith(";")])}
    if "statedb" in k and (n := newest(k["statedb"]["dir"], k["statedb"].get("pattern", "*"))):
        r = sh("zstd", "-t", "-q", str(Path(k["statedb"]["dir"]) / n["file"]), timeout=600)
        out["statedb_archive_intact"] = {"file": n["file"], "ok": r.returncode == 0}
    n_obj = int(sample if sample is not None else (cfg.get("raw_vault") or {}).get("sample", 3))
    if n_obj:
        out["raw_vault_sample"] = _raw_vault_sample(n_obj)
    out["ok"] = all(v.get("ok", True) for v in out.values() if isinstance(v, dict))
    return out


def _raw_vault_sample(n: int) -> dict:
    """A few clear-zone objects re-downloaded through Walter Memory's objects interface, which checks the sha256;
    optional: when Memory is down this proof is `unknown`, not a failure of the backups."""
    r = sh("walter-memory", "objects", "search", "", "--limit", "200", "--cloud-safe", timeout=120)
    try:
        rows = json.loads(r.stdout)
        rows = rows if isinstance(rows, list) else rows.get("results") or rows.get("objects") or []
    except ValueError:
        return {"ok": None, "error": "walter-memory objects unavailable"}
    import random
    rows = [x for x in rows if (x.get("size_bytes") or 0) < 20_000_000]
    picked = random.sample(rows, min(n, len(rows)))
    results = []
    tmp = Path(f"/var/tmp/walter-backup-verify-{os.getpid()}")
    tmp.mkdir(mode=0o700, exist_ok=True)
    try:
        for o in picked:
            ref = str(o.get("id") or o.get("sha256"))
            g = sh("walter-memory", "objects", "get", ref, "--cloud-safe", "--dest-dir", str(tmp), timeout=300)
            results.append({"object": ref[:12], "ok": g.returncode == 0})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"ok": all(x["ok"] for x in results) if results else None, "checked": results}


# ---- the module's own watchdog (G0): Incident v1 ---------------------------------------------------------------

def incident(key: str, kind: str, severity: str, summary: str, evidence: dict, level: str = "G0") -> dict:
    return {"version": INCIDENT_VERSION, "module": "backup", "key": key, "kind": kind, "severity": severity,
            "summary": summary, "evidence": evidence, "suggested_level": level}


def check() -> list[dict]:
    st, cfg = status(), config()
    out = []
    c = st["conformity"]
    if c.get("ok") is False:
        out.append(incident("conformity", "registry_drift", "warning",
                            "Le registre des modules diffère des contrats : la sauvegarde passe en mode dégradé.", c, "G1"))
    for kind, item in st["backup_health"].items():
        if not item["ok"]:
            sev = "critical" if kind == "offsite" else "high"
            out.append(incident(f"backup:{kind}", "backup_stale", sev,
                                f"Sauvegarde {kind} absente ou trop ancienne ({item.get('age_h')} h, limite "
                                f"{item.get('max_age_hours')} h).", item, "G1"))
    r = st["restorability"]
    for name in ("offsite_restore_test", "isolated_drill"):
        if name in r and not r[name].get("ok"):
            out.append(incident(f"restore:{name}", "restore_unproven", "warning",
                                f"Restauration non prouvée récemment ({name}).", r[name], "G0"))
    if not r["disk"]["drill_possible_now"]:
        out.append(incident("restore:disk", "restore_blocked", "warning",
                            f"Pas assez de disque pour l'exercice de restauration ({r['disk']['free_gib']} Gio libres, "
                            f"{r['disk']['needed_for_drill_gib']} nécessaires).", r["disk"], "G3"))
    warn = float((cfg.get("git") or {}).get("dirty_warn_hours", 48))
    for repo in git_inventory():
        if repo["dirty"] and (repo["oldest_change_age_h"] or 0) > warn:
            out.append(incident(f"git:{repo['repo']}", "uncommitted_work", "info",
                                f"Travail non commité depuis {repo['oldest_change_age_h']} h dans {repo['repo']} "
                                f"({repo['dirty']} fichiers) : il n'est dans aucune référence git.", repo, "G0"))
    return out

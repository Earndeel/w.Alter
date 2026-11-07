#!/usr/bin/env python3
"""walter-secrets-sync — Bitwarden is the source of truth for W.Alter's keys; the VM keeps a generated local copy.

Decision 2026-10-02: keys are managed in Bitwarden (folder "W.Alter – Clés API"); every change is applied
to the VM automatically. The VM never reads Bitwarden at runtime: services keep reading their env files / the age
vault, which this daemon rewrites — so W.Alter keeps working when Vaultwarden is down.

  secrets_sync.py build-map     match every local secret to its Bitwarden field (by value) → secrets-map.json
  secrets_sync.py check         dry run: which local targets differ from Bitwarden
  secrets_sync.py once          apply differences now
  secrets_sync.py watch         daemon: poll the vault revision date every 30 s; on change apply keys, file new entries
                                (vault_react), emit `vault.changed` on the bus, back up once calm (+ full pass every 6 h)

Changes: backup of every touched file first, write, restart only the units that read the file, verify they are
active, roll back automatically otherwise. Bitwarden deletions are never propagated (logged instead).
Logs / status hold item and target names only, never values.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import settings
H = settings.DATA_ROOT
FOLDER = "W.Alter – Clés API"
SERVER = settings.setting("bitwarden", "server", "")
MAP = H / "vault/secrets-map.json"
STATUS = H / "logs/walter-secrets-sync.status.json"
LOG = H / "logs/walter-secrets-sync.log"
BACKUPS = H / "backups/secrets-sync"
BW_DATA = settings.path("bitwarden_data", Path.home() / ".config/Bitwarden CLI/data.json")
VAULT_ENC, VAULT_KEY = settings.VAULT_ENC, settings.VAULT_KEY
ENV_FILES = [Path(p) for p in settings.setting("sync", "env_files", [])]
HEADER = "# Clés gérées dans Bitwarden (dossier « W.Alter – Clés API ») et appliquées par walter-secrets-sync : modifier là-bas."
POLL, FULL_EVERY, BACKUP_SETTLE = 30, 6 * 3600, 120


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    old = os.umask(0o077)
    try:
        with LOG.open("a") as f:
            f.write(line + "\n")
    finally:
        os.umask(old)


def write_private(path: Path, data: str | bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    old = os.umask(0o077)
    try:
        (tmp.write_bytes if isinstance(data, bytes) else tmp.write_text)(data)
    finally:
        os.umask(old)
    if path.exists():
        shutil.copymode(path, tmp)
    os.replace(tmp, path)


def fp(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()[:12]


# ── Bitwarden ──────────────────────────────────────────────────────────────────
def session(stale: str | None = None) -> str:
    argv, env = [str(settings.UNLOCK), "--print"], None
    if stale:
        argv, env = [str(settings.UNLOCK), "--renew"], {**os.environ, "WALTER_BW_STALE": stale}
    r = subprocess.run(argv, capture_output=True, text=True, timeout=120, env=env)
    if r.returncode or not r.stdout.strip():
        raise RuntimeError("bw-unlock failed")
    return r.stdout.strip().splitlines()[-1]


def bw(*args: str) -> str:
    sess = session()
    for attempt in (1, 2):
        r = subprocess.run(["bw", *args, "--nointeraction"], capture_output=True, text=True, timeout=180,
                           env=settings.bw_env(BW_SESSION=sess, BW_NOINTERACTION="true"))
        if not r.returncode:
            return r.stdout
        if attempt == 1 and "locked" in (r.stderr + r.stdout).lower():   # dead cached session: renew once
            from .unlock import fingerprint
            sess = session(stale=fingerprint(sess))
            continue
        break
    raise RuntimeError(f"bw {args[0]} failed (diagnostic suppressed)")


def folder_items() -> dict[str, dict]:
    bw("sync")
    fid = next((f["id"] for f in json.loads(bw("list", "folders")) if f["name"] == FOLDER), None)
    if not fid:
        raise RuntimeError(f"Bitwarden folder {FOLDER!r} not found")
    return {i["id"]: i for i in json.loads(bw("list", "items", "--folderid", fid))}


def item_fields(i: dict) -> dict[str, str]:
    """Every value of an item, keyed 'field:<name>', 'login.password', 'login.username', 'card.number'…"""
    out = {f"field:{f['name']}": f["value"] for f in i.get("fields") or [] if f.get("name") and f.get("value")}
    for part in ("login", "card"):
        for k, v in (i.get(part) or {}).items():
            if isinstance(v, str) and v:
                out[f"{part}.{k}"] = v
    return out


def revision_date() -> str | None:
    """Server-side vault revision (changes on any edit). Cheap: one authenticated GET."""
    import urllib.error
    import urllib.request
    for attempt in (1, 2):
        try:
            d = json.loads(BW_DATA.read_text())
            tok = next((v for k, v in d.items() if k.endswith("_token_accessToken")), None)
            req = urllib.request.Request(f"{SERVER}/api/accounts/revision-date",
                                         headers={"Authorization": f"Bearer {tok}"})
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read().decode().strip()
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and attempt == 1:
                try:
                    bw("sync")
                    continue
                except Exception:
                    pass
        except Exception:
            pass
        return None
    return None


# ── local targets ──────────────────────────────────────────────────────────────
def read_vault() -> dict:
    return json.loads(subprocess.run(["age", "-d", "-i", str(VAULT_KEY), str(VAULT_ENC)], capture_output=True, check=True).stdout)


def write_vault(v: dict) -> None:
    pub = next(l.split(":", 1)[1].strip() for l in VAULT_KEY.read_text().splitlines() if l.startswith("# public key:"))
    enc = subprocess.run(["age", "-r", pub], input=json.dumps(v, indent=2).encode(), capture_output=True, check=True).stdout
    write_private(VAULT_ENC, enc)


def read_env(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        m = re.match(r"^([A-Za-z0-9_]+)=(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip().strip("'\"")
    return out


def write_env(path: Path, updates: dict[str, str]) -> None:
    lines, seen = path.read_text().splitlines(), set()
    for n, line in enumerate(lines):
        m = re.match(r"^([A-Za-z0-9_]+)=(.*)$", line.strip())
        if m and m.group(1) in updates:
            q = m.group(2).strip()[:1] if m.group(2).strip()[:1] in ("'", '"') else ""
            lines[n] = f"{m.group(1)}={q}{updates[m.group(1)]}{q}"
            seen.add(m.group(1))
    if HEADER not in lines:
        lines.insert(0, HEADER)
    write_private(path, "\n".join(lines) + "\n")


def current_targets() -> dict[str, str]:
    """target id → current value. Targets: 'vault:<service>/<field>' and 'env:<file>:<VAR>'."""
    out = {}
    for svc, body in read_vault().get("services", {}).items():
        for k, v in (body.items() if isinstance(body, dict) else []):
            if not k.startswith("_") and isinstance(v, str):
                out[f"vault:{svc}/{k}"] = v
    for p in ENV_FILES:
        if p.exists():
            out.update({f"env:{p}:{k}": v for k, v in read_env(p).items()})
    return out


# ── map ────────────────────────────────────────────────────────────────────────
def build_map() -> dict:
    items = folder_items()
    by_value: dict[str, list[tuple[str, str, str]]] = {}
    for iid, i in items.items():
        for f, v in item_fields(i).items():
            if len(v) >= 12:
                by_value.setdefault(v, []).append((iid, i["name"], f))
    entries, unmapped, dupes = [], [], []
    for target, val in sorted(current_targets().items()):
        cands = by_value.get(val)
        if not cands:
            if len(val) >= 12 and re.search(r"(?i)key|token|secret|password", target.rsplit("/", 1)[-1].rsplit(":", 1)[-1]):
                unmapped.append(target)
            continue
        svc = target.split(":", 1)[1].split("/", 1)[0] if target.startswith("vault:") else None
        var = target.rsplit(":", 1)[-1]
        if len({c[0] for c in cands}) > 1:             # same value in several items: one item drives all copies
            cands = sorted(cands, key=lambda c: c[1])
        best = next((c for c in cands if svc and c[1] == f"W.Alter · {svc}" and len({x[0] for x in cands}) == 1), None) or \
            next((c for c in cands if c[1] == f"W.Alter · {var}"), None) or cands[0]
        if len({c[0] for c in cands}) > 1:
            dupes.append({"target": target, "items": sorted({c[1] for c in cands}), "chosen": best[1]})
        entries.append({"target": target, "item_id": best[0], "item": best[1], "field": best[2]})
    m = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "folder": FOLDER,
         "entries": entries, "unmapped": unmapped, "same_value_in_several_items": dupes}
    write_private(MAP, json.dumps(m, ensure_ascii=False, indent=1))
    return {"mapped": len(entries), "unmapped": unmapped, "duplicates": len(dupes)}


# ── sync ───────────────────────────────────────────────────────────────────────
def units_for(path: Path) -> list[tuple[str, bool]]:
    """(unit, is_user) reading this env file and currently active."""
    out = []
    for f in Path("/etc/systemd/system").glob("*.service"):
        try:
            text = f.read_text(errors="ignore")
        except OSError:                                   # dangling unit symlinks
            continue
        if re.search(rf"EnvironmentFile=-?{re.escape(str(path))}\s*$", text, re.M):
            if subprocess.run(["systemctl", "is-active", "--quiet", f.name]).returncode == 0:
                out.append((f.name, False))
    for consumer in settings.ENV_CONSUMERS:
        if path == Path(consumer["path"]):
            out.append((consumer["unit"], bool(consumer.get("user"))))
    return out


def restart(units: list[tuple[str, bool]]) -> list[str]:
    failed = []
    env = {**os.environ, "XDG_RUNTIME_DIR": "/run/user/0"}
    for unit, user in units:
        override = next((c.get("restart") for c in settings.ENV_CONSUMERS
                         if c["unit"] == unit and bool(c.get("user")) == user), None)
        command = override or ["systemctl", *(["--user"] if user else []), "restart", unit]
        subprocess.run(command, env=env, capture_output=True, timeout=300)
    time.sleep(15)
    for unit, user in units:
        if subprocess.run(["systemctl", *(["--user"] if user else []), "is-active", "--quiet", unit], env=env).returncode:
            failed.append(unit)
    return failed


def plan(items: dict[str, dict]) -> tuple[list[dict], list[str]]:
    m = json.loads(MAP.read_text())
    cur = current_targets()
    changes, missing = [], []
    for e in m["entries"]:
        i = items.get(e["item_id"])
        new = item_fields(i).get(e["field"]) if i else None
        if new is None:
            missing.append(f"{e['item']} / {e['field']} → {e['target']}")
            continue
        if cur.get(e["target"]) != new:
            changes.append({**e, "value": new})
    return changes, missing


def apply(changes: list[dict]) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bdir = BACKUPS / ts
    bdir.mkdir(parents=True, mode=0o700)
    vault_changes = [c for c in changes if c["target"].startswith("vault:")]
    env_changes: dict[Path, dict[str, str]] = {}
    for c in changes:
        if c["target"].startswith("env:"):
            _, path, var = c["target"].split(":", 2)
            env_changes.setdefault(Path(path), {})[var] = c["value"]
    units = sorted({u for p in env_changes for u in units_for(p)})   # before any write
    touched = ([VAULT_ENC] if vault_changes else []) + list(env_changes)
    for p in touched:
        shutil.copy2(p, bdir / p.as_posix().strip("/").replace("/", "__"))
    if vault_changes:
        v = read_vault()
        for c in vault_changes:
            svc, field = c["target"][6:].split("/", 1)
            v["services"][svc][field] = c["value"]
        write_vault(v)
    for p, upd in env_changes.items():
        write_env(p, upd)
    failed = restart(units) if units else []
    if failed:
        for p in touched:
            shutil.copy2(bdir / p.as_posix().strip("/").replace("/", "__"), p)
        restart(units)
        log(f"ROLLBACK: units failed after update {failed}; files restored from {bdir}")
        return {"applied": 0, "rolled_back": True, "failed_units": failed, "backup": str(bdir)}
    for c in changes:
        log(f"updated {c['target']} from Bitwarden '{c['item']}' {c['field']}")
    if units:
        log(f"restarted {[u for u, _ in units]}")
    return {"applied": len(changes), "restarted": [u for u, _ in units], "backup": str(bdir)}


def sync_once(dry: bool = False) -> dict:
    items = folder_items()
    changes, missing = plan(items)
    for mm in missing:
        log(f"WARNING Bitwarden source missing (not propagated): {mm}")
    if dry or not changes:
        return {"changes": [f"{c['target']} ← {c['item']} {c['field']}" for c in changes], "missing": missing}
    return {**apply(changes), "missing": missing}


def status(**kw) -> None:
    s = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    s.update(kw)
    write_private(STATUS, json.dumps(s, ensure_ascii=False, indent=1))


def watch() -> None:
    """One watcher for the whole vault: on every revision change, (1) apply W.Alter's keys to the VM, (2) file new
    entries into their folder, (3) announce `vault.changed` on the Walter bus, then (4) once the vault has been calm
    for BACKUP_SETTLE seconds, take one encrypted backup (a burst of edits → one backup). See vault_react.py."""
    from . import vault_react
    from walter_memory import bus
    last_rev, last_full, changed_at = None, 0.0, None
    log("watch started")
    while True:
        now = time.time()
        rev = revision_date()
        status(last_check=datetime.now(timezone.utc).isoformat(timespec="seconds"), server_reachable=rev is not None)
        if rev is not None and (rev != last_rev or now - last_full > FULL_EVERY):
            if rev != last_rev:
                changed_at = now
            try:
                res = sync_once()
                status(last_sync=datetime.now(timezone.utc).isoformat(timespec="seconds"), last_result=res, last_error=None)
            except Exception as e:
                log(f"ERROR sync failed: {type(e).__name__}")
                status(last_error=f"{type(e).__name__}")
            try:
                filed = vault_react.file_new()
                status(last_filing=filed)
            except Exception as e:
                log(f"ERROR filing failed: {type(e).__name__}")
            if rev != last_rev and last_rev is not None:
                bus.emit("vault.changed", "walter-secrets-sync", "bitwarden", {"revision": rev}, dedupe_key=f"vault:{rev}")
            last_rev, last_full = rev, now
        if changed_at is not None and now - changed_at >= BACKUP_SETTLE:
            try:
                status(last_backup=vault_react.backup(), last_backup_error=None)
                changed_at = None
            except Exception as e:
                log(f"ERROR backup failed: {type(e).__name__}")
                status(last_backup_error=f"{type(e).__name__}")
                changed_at = now                  # retry after another settle period
        time.sleep(POLL)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "build-map":
        print(json.dumps(build_map(), ensure_ascii=False, indent=1))
    elif cmd == "check":
        print(json.dumps(sync_once(dry=True), ensure_ascii=False, indent=1))
    elif cmd == "once":
        print(json.dumps(sync_once(), ensure_ascii=False, indent=1))
    elif cmd == "watch":
        watch()
    else:
        sys.exit(__doc__)

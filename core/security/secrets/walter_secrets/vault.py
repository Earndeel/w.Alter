"""Bitwarden (self-hosted Vaultwarden) access for W.Alter — decision 2026-10-02: W.Alter has autonomous access to all of
The owner's secrets (passwords, API keys, cards, identities, document scans); nobody else does.

Values are meant to be USED, not read: tools and commands reference them with placeholders `{{bw:<item>:<field>}}`,
resolved locally right before execution and masked again in every tool result. The model (and therefore its provider)
only ever sees the placeholder, unless W.Alter explicitly calls secret_reveal.

Unlock: ~/.hermes/bin/bw-unlock (master password from the age-encrypted W.Alter vault, session cached 0600).
Audit: ~/.hermes/logs/walter-secrets.jsonl — item, field, action, tool; never a value.
"""
from __future__ import annotations

import json
import os
import re
import secrets as _rand
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .settings import UNLOCK, AUDIT, FILES
# FILES is a tmpfs location, explicitly configured.
#          # tmpfs: decrypted documents never touch the disk
FILE_TTL = 2 * 3600
LIST_TTL, SYNC_TTL = 600, 1800
MIN_MASK = 8                                      # shorter values (PINs, CVC) are too ambiguous to mask in free text
PLACEHOLDER = re.compile(r"\{\{bw:([^:{}]+):([^{}]+)\}\}")
TYPES = {1: "login", 2: "note", 3: "card", 4: "identity", 5: "ssh_key"}


def _safe_uri(value: str) -> str:
    """URLs in vault metadata may themselves contain credentials or signed queries."""
    from urllib.parse import urlsplit
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https", "androidapp", "iosapp") or not parsed.hostname:
            return "[private-uri]"
        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{host}{port}"
    except (TypeError, ValueError):
        return "[private-uri]"


class SecretError(RuntimeError):
    pass


class Vault:
    def __init__(self):
        self._lock = threading.RLock()
        self._items: list[dict] = []
        self._listed = self._synced = 0.0

    # ── bw plumbing ────────────────────────────────────────────────────────────
    def _session(self, stale: str | None = None) -> str:
        argv, env = [str(UNLOCK), "--print"], None
        if stale:   # the cached session was refused: renew it (fingerprint only, never the session itself)
            argv, env = [str(UNLOCK), "--renew"], {**os.environ, "WALTER_BW_STALE": stale}
        r = subprocess.run(argv, capture_output=True, text=True, timeout=120, env=env)
        s = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        if r.returncode or not s:
            raise SecretError("Bitwarden unlock failed (bw-unlock)")
        return s

    def _bw(self, *args: str, timeout: int = 120) -> str:
        session = self._session()
        for attempt in (1, 2):
            env = {**os.environ, "BW_SESSION": session, "BW_NOINTERACTION": "true"}
            r = subprocess.run(["bw", *args, "--nointeraction"], capture_output=True, text=True, timeout=timeout, env=env)
            if not r.returncode:
                return r.stdout
            if attempt == 1 and "locked" in (r.stderr + r.stdout).lower():
                # a dead cached session (another `bw unlock` superseded it): renew once and retry
                from .unlock import fingerprint
                session = self._session(stale=fingerprint(session))
                continue
            break
        raise SecretError(f"bw {args[0]} failed (diagnostic suppressed)")

    def items(self) -> list[dict]:
        with self._lock:
            now = time.time()
            if now - self._synced > SYNC_TTL:
                try:
                    self._bw("sync")
                except SecretError:
                    pass                           # offline server: keep serving the local encrypted cache
                self._synced, self._listed = now, 0.0
            if now - self._listed > LIST_TTL or not self._items:
                self._items = [i for i in json.loads(self._bw("list", "items")) if not i.get("deletedDate")]
                self._listed = now
            return self._items

    # ── lookup ─────────────────────────────────────────────────────────────────
    def find(self, ref: str) -> dict:
        ref = ref.strip()
        items = self.items()
        for i in items:
            if i["id"] == ref:
                return i
        exact = [i for i in items if i["name"].lower() == ref.lower()]
        if len(exact) == 1:
            return exact[0]
        part = exact or [i for i in items if ref.lower() in i["name"].lower()]
        if len(part) == 1:
            return part[0]
        if not part:
            raise SecretError(f"no Bitwarden item matches {ref!r} (use secret_search)")
        raise SecretError(f"{len(part)} items match {ref!r}: " + "; ".join(f"{i['name']} = {i['id']}" for i in part[:8]))

    @staticmethod
    def describe(i: dict) -> dict:
        """Everything useful to choose and use an item — no secret value."""
        t = TYPES.get(i.get("type"), str(i.get("type")))
        d = {"id": i["id"], "name": i["name"], "type": t, "favorite": i.get("favorite", False),
             "updated": (i.get("revisionDate") or "")[:10]}
        fields = []
        if t == "login":
            lg = i.get("login") or {}
            d["username"] = lg.get("username")
            d["uris"] = [_safe_uri(u.get("uri")) for u in lg.get("uris") or [] if u.get("uri")][:5]
            fields += [f for f in ("username", "password") if lg.get(f)] + (["totp"] if lg.get("totp") else [])
        elif t == "card":
            c = i.get("card") or {}
            d["card"] = {"brand": c.get("brand"), "last4": (c.get("number") or "")[-4:] or None,
                         "holder": c.get("cardholderName"), "exp": f"{c.get('expMonth') or '?'}/{c.get('expYear') or '?'}"}
            fields += [f for f in ("number", "code", "expMonth", "expYear", "cardholderName") if c.get(f)]
        elif t == "identity":
            idn = i.get("identity") or {}
            d["identity"] = " ".join(x for x in (idn.get("firstName"), idn.get("lastName")) if x) or None
            fields += [k for k, v in idn.items() if v]
        if i.get("notes"):
            fields.append("notes")
        fields += [f"field:{f['name']}" for f in i.get("fields") or [] if f.get("name")]
        d["fields"] = fields
        d["attachments"] = [{"name": a["fileName"], "size": a.get("sizeName")} for a in i.get("attachments") or []]
        return d

    def search(self, query: str = "", kind: str | None = None, limit: int = 20) -> list[dict]:
        words = [w for w in query.lower().split() if w]
        out = []
        for i in self.items():
            d = self.describe(i)
            if kind and d["type"] != kind:
                continue
            hay = " ".join([i["name"], d.get("username") or "", *d.get("uris", []), d.get("identity") or "",
                            *(a["name"] for a in d["attachments"]), *(f for f in d["fields"] if f.startswith("field:"))]).lower()
            if all(w in hay for w in words):
                out.append(d)
        out.sort(key=lambda d: (not d["favorite"], d["name"].lower()))
        return out[:limit]

    def value(self, ref: str, field: str) -> str:
        i = self.find(ref)
        f = field.strip()
        t = TYPES.get(i.get("type"))
        if f == "totp":
            return self._bw("get", "totp", i["id"]).strip()
        if f == "notes":
            v = i.get("notes")
        elif f.startswith("field:") or f not in ("username", "password", "uri", "number", "code", "expMonth", "expYear",
                                                 "cardholderName", "brand") and t != "identity":
            name = f.removeprefix("field:")
            v = next((x.get("value") for x in i.get("fields") or [] if x.get("name") == name), None)
        elif t == "login":
            lg = i.get("login") or {}
            v = (lg.get("uris") or [{}])[0].get("uri") if f == "uri" else lg.get(f)
        elif t == "card":
            v = (i.get("card") or {}).get(f)
        elif t == "identity":
            v = (i.get("identity") or {}).get(f)
        else:
            v = None
        if v in (None, ""):
            raise SecretError(f"item {i['name']!r} has no field {f!r} (fields: {', '.join(self.describe(i)['fields'])})")
        return str(v)

    def attachment(self, ref: str, name: str | None = None) -> Path:
        i = self.find(ref)
        atts = i.get("attachments") or []
        a = next((x for x in atts if name and x["fileName"].lower() == name.lower()), None) or \
            (atts[0] if len(atts) == 1 and not name else None)
        if not a:
            raise SecretError(f"item {i['name']!r} attachments: {[x['fileName'] for x in atts] or 'none'} — pick one by name")
        cleanup_files()
        d = FILES / _rand.token_hex(8)
        d.mkdir(parents=True, mode=0o700)
        out = d / re.sub(r"[/\\\x00]", "_", a["fileName"])
        self._bw("get", "attachment", a["id"], "--itemid", i["id"], "--output", str(out), timeout=300)
        os.chmod(out, 0o600)
        return out

    def maskable(self) -> dict[str, str]:
        """value → placeholder for every long-enough secret in the vault (used to mask tool results)."""
        out = {}
        for i in self.items():
            t = TYPES.get(i.get("type"))
            cand = []
            if t == "login":
                cand.append(("password", (i.get("login") or {}).get("password")))
            elif t == "card":
                c = i.get("card") or {}
                cand.append(("number", c.get("number")))
            elif t == "identity":
                idn = i.get("identity") or {}
                cand += [(k, idn.get(k)) for k in ("ssn", "passportNumber", "licenseNumber")]
            cand += [(f"field:{f['name']}", f.get("value")) for f in i.get("fields") or [] if f.get("type") == 1]
            for field, v in cand:
                if isinstance(v, str) and len(v) >= MIN_MASK:
                    out[v] = f"{{{{bw:{i['id']}:{field}}}}}"
        return out


def cleanup_files() -> None:
    if not FILES.exists():
        FILES.mkdir(parents=True, mode=0o700)
        return
    for d in FILES.iterdir():
        if time.time() - d.stat().st_mtime > FILE_TTL:
            shutil.rmtree(d, ignore_errors=True)


def audit(action: str, item: dict | None = None, field: str | None = None, **extra) -> None:
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "action": action,
           "item": item["name"] if item else None, "item_id": item["id"] if item else None, "field": field, **extra}
    old = os.umask(0o077)
    try:
        with AUDIT.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    finally:
        os.umask(old)


VAULT = Vault()

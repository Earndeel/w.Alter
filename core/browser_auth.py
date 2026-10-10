#!/usr/bin/env python3
"""browser_auth — open a Camoufox session logged in as Monsieur, without any agent touching his cookies.

The agent asks for a *site* (google, meta, linkedin…, see browser_sites.json); this module, server-side:
  1. takes a consistent copy of Monsieur's Brave cookie database on the Mac (SSH, sqlite backup API),
     keeping only the cookies of that site's domains;
  2. decrypts them with the Brave Safe Storage password held in the vault;
  3. injects them into an isolated Camoufox Max browser context (userId = session name);
  4. checks the login with a real navigation and returns only metadata: session name, cookie count per host,
     authenticated yes/no, final URL. Cookie values never leave this process and are never logged.

The agent then drives the browser through the Camoufox HTTP API (127.0.0.1:9377) with that userId.

CLI (timers, manual checks):  browser_auth.py login google [--session flow]   |   browser_auth.py sites
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

CONFIG = Path(os.environ.get("WALTER_BROWSER_SITES", Path(__file__).with_name("browser_sites.json")))
CAMOUFOX = os.environ.get("WALTER_CAMOUFOX_URL", "http://127.0.0.1:9377")
AUDIT_LOG = Path(os.environ.get("WALTER_BROWSER_AUDIT", "/root/.hermes/logs/browser-session.log"))
ANALYTICS = ("_ga", "_gcl", "_gat", "_gid", "_dd", "_fbp", "_hj", "_uet", "_clck", "_clsk")
SESSION_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
CHROME_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01

# Runs on the Mac (stdlib only). Consistent copy via the sqlite backup API (Brave may be writing), filtered
# to the requested domains, temp copy deleted. Prints one JSON document on stdout.
REMOTE = r'''
import json, os, sqlite3, sys, tempfile
args = json.loads(sys.argv[1])
src = os.path.expanduser(args["db"])
fd, tmp = tempfile.mkstemp(suffix=".db"); os.close(fd)
try:
    s = sqlite3.connect("file:" + src + "?mode=ro", uri=True); d = sqlite3.connect(tmp)
    s.backup(d); s.close()
    ver = int((d.execute("select value from meta where key='version'").fetchone() or [0])[0])
    where = " or ".join(["host_key = ? or host_key like ?"] * len(args["domains"]))
    params = [p for dom in args["domains"] for p in (dom, "%." + dom)]
    rows = d.execute("select host_key, name, value, hex(encrypted_value), path, expires_utc, is_secure, "
                     "is_httponly, samesite from cookies where " + where, params).fetchall()
    d.close()
    print(json.dumps({"version": ver, "rows": rows}))
finally:
    os.unlink(tmp)
'''


def load_config() -> dict:
    return json.loads(CONFIG.read_text())


def _vault(entry: str) -> str:
    r = subprocess.run(["vault", "get", entry], capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"vault entry '{entry}' unavailable (check settings.brave_key_vault_entry)")
    return r.stdout.strip()


def _brave_key(entry: str) -> bytes:
    secret = _vault(entry)
    if re.fullmatch(r"[0-9a-fA-F]{32}", secret):  # already the derived AES-128 key
        return bytes.fromhex(secret)
    return hashlib.pbkdf2_hmac("sha1", secret.encode(), b"saltysalt", 1003, dklen=16)  # Keychain password


def _decrypt(enc_hex: str, host: str, key: bytes, db_version: int) -> str | None:
    blob = bytes.fromhex(enc_hex)
    if blob[:3] not in (b"v10", b"v11"):
        return None
    dec = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
    plain = dec.update(blob[3:]) + dec.finalize()
    pad = plain[-1] if plain else 0
    if not 1 <= pad <= 16:
        return None
    plain = plain[:-pad]
    # Chromium ≥ DB v24 prefixes the plaintext with SHA-256(host_key); verify it rather than guess.
    if db_version >= 24 and plain[:32] == hashlib.sha256(host.encode()).digest():
        plain = plain[32:]
    try:
        value = plain.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return value if value.isprintable() else None


def _fetch_rows(domains: list[str], settings: dict) -> dict:
    payload = json.dumps({"db": settings.get("brave_cookies_db",
                                             "~/Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies"),
                          "domains": domains})
    remote = "python3 -c " + shlex.quote(REMOTE) + " " + shlex.quote(payload)
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if settings.get("ssh_identity"):
        cmd += ["-o", "IdentitiesOnly=yes", "-i", os.path.expanduser(settings["ssh_identity"])]
    r = subprocess.run([*cmd, settings.get("ssh_host", "mac"), remote], capture_output=True, text=True, timeout=90)
    if r.returncode != 0:
        raise RuntimeError(f"Mac unreachable or Brave DB unreadable (ssh exit {r.returncode}): {r.stderr.strip()[-300:]}")
    return json.loads(r.stdout)


def _to_playwright(row: list, value: str) -> dict | None:
    host, name, _, _, path, expires_utc, secure, httponly, samesite = row
    same = {0: "None", 1: "Lax", 2: "Strict"}.get(samesite, "Lax")
    if same == "None" and not secure:
        same = "Lax"
    c = {"name": name, "value": value, "domain": host, "path": path or "/", "secure": bool(secure),
         "httpOnly": bool(httponly), "sameSite": same}
    if expires_utc:
        exp = expires_utc / 1_000_000 - CHROME_EPOCH_OFFSET
        if exp < time.time():
            return None
        c["expires"] = int(exp)
    if name.startswith("__Host-"):
        c["domain"] = host.lstrip(".")
    return c


def _camoufox(path: str, body: dict, timeout: float = 60) -> dict:
    r = httpx.post(f"{CAMOUFOX}{path}", json=body, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"Camoufox {path} → HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def _inject(session: str, cookies: list[dict]) -> tuple[int, int]:
    try:
        _camoufox("/session/cookies", {"userId": session, "cookies": cookies})
        return len(cookies), 0
    except RuntimeError:  # one malformed cookie rejects the whole batch: retry one by one
        ok = bad = 0
        for c in cookies:
            try:
                _camoufox("/session/cookies", {"userId": session, "cookies": [c]})
                ok += 1
            except RuntimeError:
                bad += 1
        return ok, bad


def _verify(session: str, site: dict) -> dict:
    check = site.get("check") or {}
    if not check.get("url"):
        return {"authenticated": None, "note": "no check configured for this site"}
    tab = _camoufox("/tab/new", {"userId": session, "listItemId": "auth-check"})["tabId"]
    try:
        nav = _camoufox("/tab/navigate", {"userId": session, "tabId": tab, "url": check["url"]}, timeout=90)
        time.sleep(float(check.get("settle_s", 4)))
        snap = _camoufox("/tab/snapshot", {"userId": session, "tabId": tab}, timeout=60)
        url = str(snap.get("url") or nav.get("url") or "")
        text = str(snap.get("snapshot") or "")
        signed_out = any(p in url for p in check.get("signed_out_url", [])) or \
            any(m in text for m in check.get("signed_out_text", []))
        signed_in = any(m in text for m in check["signed_in_text"]) if check.get("signed_in_text") else True
        return {"authenticated": bool(signed_in and not signed_out), "final_url": url.split("?")[0]}
    finally:
        try:
            _camoufox("/tab/close", {"userId": session, "tabId": tab})
        except RuntimeError:
            pass


def _audit(entry: dict) -> None:
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        os.chmod(AUDIT_LOG, 0o600)
    except OSError:
        pass


def login(site_name: str, session: str = "", client: str = "cli", verify: bool = True) -> dict:
    """Inject Monsieur's Brave cookies for one configured site into Camoufox session `session`. Metadata only."""
    cfg = load_config()
    site = cfg.get("sites", {}).get(site_name)
    if not site:
        raise ValueError(f"unknown site '{site_name}'; configured: {', '.join(sorted(cfg.get('sites', {})))}")
    session = session or f"{site_name}-me"
    if not SESSION_RE.match(session):
        raise ValueError("session must match [a-z0-9][a-z0-9_-]{1,40}")
    settings = cfg.get("settings", {})
    started = time.time()
    data = _fetch_rows(site["domains"], settings)
    key = _brave_key(settings["brave_key_vault_entry"])
    cookies, undecryptable, expired, hosts = [], 0, 0, {}
    for row in data["rows"]:
        if row[1].startswith(ANALYTICS):
            continue
        value = row[2] or _decrypt(row[3], row[0], key, data["version"])
        if value is None:
            undecryptable += 1
            continue
        c = _to_playwright(row, value)
        if c is None:
            expired += 1
            continue
        cookies.append(c)
        host = row[0].lstrip(".")
        hosts[host] = hosts.get(host, 0) + 1
    if not cookies:
        raise RuntimeError(f"no usable cookie for {site_name} in Brave (undecryptable={undecryptable}, "
                           f"expired={expired}); is Monsieur logged in on Brave?")
    missing = [n for n in site.get("required_cookies", []) if n not in {c["name"] for c in cookies}]
    injected, rejected = _inject(session, cookies)
    result = {"site": site_name, "session": session, "cookies_injected": injected, "rejected": rejected,
              "undecryptable": undecryptable, "expired_skipped": expired, "missing_required": missing,
              "hosts": dict(sorted(hosts.items(), key=lambda x: -x[1])[:12])}
    if verify:
        result.update(_verify(session, site))
    result["seconds"] = round(time.time() - started, 1)
    result["drive_with"] = f"Camoufox HTTP API {CAMOUFOX} (/tab/new, /tab/navigate, /tab/snapshot…) userId={session}"
    _audit({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "client": client,
            **{k: result[k] for k in ("site", "session", "cookies_injected", "rejected", "missing_required")},
            "authenticated": result.get("authenticated")})
    return result


def sites() -> dict:
    return {name: {"domains": s["domains"], "check": (s.get("check") or {}).get("url")}
            for name, s in load_config().get("sites", {}).items()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("login")
    lg.add_argument("site")
    lg.add_argument("--session", default="")
    lg.add_argument("--no-verify", action="store_true")
    sub.add_parser("sites")
    a = ap.parse_args()
    try:
        out = sites() if a.cmd == "sites" else login(a.site, a.session, client="cli", verify=not a.no_verify)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(out, ensure_ascii=False, indent=2))

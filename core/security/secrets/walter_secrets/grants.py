"""Walter's authorizations (grants): one registry, one renewer per grant, access through one interface.

A grant is anything that lets Walter act somewhere: its own identities (its Telegram bot, its subscription sessions,
its Google Cloud client, its tunnels) and access delegated to the owner's accounts (Gmail and Calendar reading,
Beeper, the Drive of the Raw Vault). Modules ask `access(id)` (or `walter-secret grant access|exec`); they never read
a token file themselves, and only the grant's renewer refreshes it.

Cards (no secret): the active instance's accounts/<id>.toml —
    title, owner = "walter" | "owner", kind = api_key | bot | oauth | subscription | tunnel | storage | cookies,
    provider, scopes, consumers, renewer = "walter-secrets" | "vendor:<cli>" | "none", notes
    [secret]   token = "<storage>", client = "<storage>" (OAuth client, optional), any other named secret part
    [attributes] non-secret values kept next to the grant (account id, login e-mail…), same storage forms
    allow = ["<component>", …]  components allowed to read it; when present, every read names its reader
               (`access(id, consumer=…)`, `walter-secret grant access <id> --as <component>`) and others are refused
    [env]      NAME = "<part>" | "attribute:<key>": the variable name a component knows the secret by (provider
               configs, third-party CLIs). `env_value(NAME, consumer)` and `environment(ids, consumer)` resolve them;
               the only source is the grant's storage — there is no env-file or Hermes fallback (2026-11-11).
Storage: "vault:<item>#<field>" (Bitwarden), "file:<path>" or "file:<path>#<dotted.json.key>" (a declared private
file, while the grant still lives at its historical place), "external:<where>" (not readable from here).
All processes run as the same system user: `allow` is an enforced contract plus an audit trail (every read records
grant, part and reader, never a value), not an operating-system barrier.
"""
from __future__ import annotations

import base64
import fcntl
import json
import os
import stat
import subprocess
import threading
import time
import tomllib
import tempfile
from pathlib import Path

from . import settings

KINDS = {"api_key", "bot", "oauth", "subscription", "tunnel", "storage", "cookies"}
OWNERS = {"walter", "owner"}
REFRESH_MARGIN = {"oauth": 60, "subscription": 3600}
_lock = threading.Lock()


class GrantError(RuntimeError):
    pass


# ── registry ───────────────────────────────────────────────────────────────────────────────────────────────
def accounts_dir() -> Path:
    if os.environ.get("WALTER_GRANTS_DIR"):
        return Path(os.environ["WALTER_GRANTS_DIR"])
    root = settings._walter_instance("path")
    if root is None:
        raise GrantError("no active Walter instance")
    return root / "accounts"


def _validate(card: dict, ident: str) -> dict:
    if card.get("kind") not in KINDS:
        raise GrantError(f"grant {ident}: unknown kind {card.get('kind')!r}")
    if card.get("owner") not in OWNERS:
        raise GrantError(f"grant {ident}: owner must be walter or owner")
    if not isinstance(card.get("secret"), dict) or not isinstance(card["secret"].get("token"), str):
        raise GrantError(f"grant {ident}: [secret] token storage required")
    for v in card["secret"].values():
        if not isinstance(v, str) or v.split(":", 1)[0] not in ("vault", "file", "external"):
            raise GrantError(f"grant {ident}: storage must be vault:, file: or external:")
    allow = card.get("allow")
    if allow is not None and (not isinstance(allow, list) or not all(isinstance(a, str) and a for a in allow)):
        raise GrantError(f"grant {ident}: allow must be a list of component names")
    for name, part in (card.get("env") or {}).items():
        attr = part.split(":", 1)[1] if isinstance(part, str) and part.startswith("attribute:") else None
        if not isinstance(part, str) or (attr is None and part not in card["secret"]) or \
                (attr is not None and attr not in (card.get("attributes") or {})):
            raise GrantError(f"grant {ident}: env {name} points to an undeclared part {part!r}")
    return {"id": ident, "title": "", "provider": "", "scopes": [], "consumers": [], "renewer": "none",
            "notes": "", **card}


def cards() -> list[dict]:
    d = accounts_dir()
    return [card(p.stem) for p in sorted(d.glob("*.toml"))] if d.is_dir() else []


def card(ident: str) -> dict:
    p = accounts_dir() / f"{ident}.toml"
    if not p.is_file() or "/" in ident:
        raise GrantError(f"unknown grant {ident!r}")
    return _validate(tomllib.loads(p.read_text()), ident)


# ── storage ────────────────────────────────────────────────────────────────────────────────────────────────
def _split(storage: str) -> tuple[str, str, str | None]:
    scheme, rest = storage.split(":", 1)
    where, _, key = rest.partition("#")
    return scheme, where, key or None


def _file(where: str) -> Path:
    p = Path(where).expanduser()
    if not p.is_absolute():
        raise GrantError("grant file path must be absolute")
    return p


def _dig(doc, key: str | None):
    for part in (key.split(".") if key else []):
        doc = doc.get(part) if isinstance(doc, dict) else None
    return doc


def _read(storage: str, audit_as: str | None = None, consumer: str | None = None):
    scheme, where, key = _split(storage)
    if scheme == "vault":
        from .vault import VAULT, audit
        if not key:
            raise GrantError("vault storage needs #field")
        value = VAULT.value(where, key)
        if audit_as:
            audit("grant", VAULT.find(where), key, grant=audit_as, **({"consumer": consumer} if consumer else {}))
        return value
    if scheme == "file":
        p = _file(where)
        text = p.read_text()
        if key is None:
            return text.strip()
        value = _dig(json.loads(text), key)
        if value is None:
            raise GrantError(f"{p.name} has no {key}")
        return value
    raise GrantError("external grant: not readable from Walter (" + where + ")")


def _jwt_exp(token: str) -> float:
    part = token.split(".")[1]
    return float(json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("exp", 0))


# ── access (one renewer per grant) ─────────────────────────────────────────────────────────────────────────
def _oauth_access(c: dict) -> str:
    """OAuth token file {refresh_token, access_token, expires_at}: walter-secrets is the only one refreshing it."""
    scheme, where, _ = _split(c["secret"]["token"])
    if scheme != "file":
        raise GrantError(f"grant {c['id']}: OAuth tokens are kept in a private file")
    path = _file(where)
    with _lock:
        tok = json.loads(path.read_text())
        if tok.get("expires_at", 0) - REFRESH_MARGIN["oauth"] >= time.time() and tok.get("access_token"):
            return tok["access_token"]
        if c["renewer"] != "walter-secrets":
            raise GrantError(f"grant {c['id']}: access token expired and {c['renewer']} renews it")
        import httpx
        client = _read(c["secret"]["client"])
        client = json.loads(client) if isinstance(client, str) else client
        r = httpx.post(client.get("token_uri", "https://oauth2.googleapis.com/token"), timeout=60, data={
            "client_id": client["client_id"], "client_secret": client["client_secret"],
            "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"})
        if r.status_code >= 400:
            raise GrantError(f"grant {c['id']}: refresh refused (HTTP {r.status_code})")
        d = r.json()
        tok.update(access_token=d["access_token"], expires_at=time.time() + d["expires_in"])
        tmp = path.with_name(path.name + ".tmp")
        old = os.umask(0o077)
        try:
            tmp.write_text(json.dumps(tok))
        finally:
            os.umask(old)
        tmp.replace(path)
        return tok["access_token"]


def _subscription_access(c: dict) -> str:
    """A vendor CLI session (e.g. Codex): the CLI stays the single writer; we make it refresh, then re-read."""
    if c.get("provider") == "anthropic-claude":
        return _claude_subscription_access(c)
    storage = c["secret"]["token"]
    tok = str(_read(storage) or "")
    if tok and _jwt_exp(tok) - time.time() > REFRESH_MARGIN["subscription"]:
        return tok
    with _lock:
        tok = str(_read(storage) or "")
        if (not tok or _jwt_exp(tok) - time.time() <= REFRESH_MARGIN["subscription"]) and c["renewer"] == "vendor:codex":
            subprocess.run(["codex", "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
                            "-c", "model_reasoning_effort=low", "Réponds OK."], capture_output=True, timeout=180,
                           cwd="/tmp")
            tok = str(_read(storage) or "")
    if not tok or _jwt_exp(tok) <= time.time():
        raise GrantError(f"grant {c['id']}: no valid session (log in again with the vendor CLI)")
    return tok


def _claude_subscription_access(c: dict) -> str:
    """Refresh an opaque Claude OAuth token once across all processes; only this grant is a writer.

    Token shape remains CLI-compatible, but the CLI receives only the current access token in memory.
    It never reads or rotates this private file. The OAuth client is public (PKCE), with no client secret.
    """
    import httpx
    scheme, where, _ = _split(c["secret"]["token"])
    if scheme != "file" or c.get("renewer") != "walter-secrets":
        raise GrantError("Claude subscription requires a private file and walter-secrets as renewer")
    path = _file(where)
    descriptor = os.open(str(path) + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        document = json.loads(path.read_text())
        token = document.get("claudeAiOauth") or {}
        if token.get("accessToken") and token.get("expiresAt", 0) / 1000 - time.time() > 300:
            return token["accessToken"]
        if not token.get("refreshToken"):
            raise GrantError("Claude subscription needs a new owner login")
        response = httpx.post("https://platform.claude.com/v1/oauth/token", timeout=30, json={
            "grant_type": "refresh_token", "refresh_token": token["refreshToken"],
            "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
            "scope": " ".join(token.get("scopes") or ["user:profile", "user:inference"])})
        if response.status_code != 200:
            raise GrantError(f"Claude subscription refresh refused (HTTP {response.status_code})")
        fresh = response.json()
        if not fresh.get("access_token") or float(fresh.get("expires_in", 0)) <= 0:
            raise GrantError("Claude subscription refresh response invalid")
        token.update(accessToken=fresh["access_token"], refreshToken=fresh.get("refresh_token") or token["refreshToken"],
                     expiresAt=int((time.time() + float(fresh["expires_in"])) * 1000))
        if fresh.get("scope"):
            token["scopes"] = fresh["scope"].split()
        document["claudeAiOauth"] = token
        fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as output:
                json.dump(document, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return token["accessToken"]


def _allowed(c: dict, consumer: str | None) -> None:
    allow = c.get("allow")
    if allow is None:
        return
    if not consumer or consumer not in allow:
        raise GrantError(f"grant {c['id']}: {consumer or 'an unnamed reader'} is not allowed (allow = {', '.join(allow)})")


# Static secrets (API keys, attributes) read from Bitwarden are kept in this process only, for CACHE_S: a Bitwarden
# read takes seconds. Nothing is ever written to disk.
CACHE_S = 900
_values: dict[tuple[str, str], tuple[float, str]] = {}


def _static(c: dict, part: str, storage: str, consumer: str | None) -> str:
    key = (c["id"], part)
    hit = _values.get(key)
    if hit and time.time() - hit[0] < CACHE_S:
        return hit[1]
    value = _read(storage, audit_as=c["id"], consumer=consumer)
    value = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
    if c["kind"] not in ("oauth", "subscription"):
        _values[key] = (time.time(), value)
    return value


def access(ident: str, part: str = "token", consumer: str | None = None) -> str:
    """The usable secret of a grant (a fresh access token for OAuth and subscriptions). Never log it."""
    c = card(ident)
    _allowed(c, consumer)
    if part != "token":
        if part not in c["secret"]:
            raise GrantError(f"grant {ident}: no secret part {part!r}")
        return _static(c, part, c["secret"][part], consumer)
    if c["kind"] == "oauth":
        return _oauth_access(c)
    if c["kind"] == "subscription":
        return _subscription_access(c)
    return _static(c, "token", c["secret"]["token"], consumer)


def _part(c: dict, part: str, consumer: str | None) -> str:
    if part.startswith("attribute:"):
        return attribute(c["id"], part.split(":", 1)[1], consumer=consumer)
    return access(c["id"], part, consumer=consumer)


def env_value(name: str, consumer: str) -> str:
    """The secret a component knows as NAME (provider configs, third-party tools), from the first grant that
    declares NAME in [env] and allows `consumer`. Raises GrantError when none does — never falls back elsewhere."""
    declaring = [c for c in cards() if name in (c.get("env") or {})]
    if not declaring:
        raise GrantError(f"{name}: no grant declares it")
    usable = [c for c in declaring if consumer in (c.get("allow") or [])]
    if not usable:
        raise GrantError(f"{name}: {consumer} is not allowed by {', '.join(c['id'] for c in declaring)}")
    c = usable[0]
    return _part(c, c["env"][name], consumer)


def environment(idents: list[str], consumer: str) -> dict[str, str]:
    """Every [env] variable of these grants, for one targeted injection (a third-party CLI that only reads its
    environment). Only the named grants' variables, only for an allowed consumer."""
    out: dict[str, str] = {}
    for ident in idents:
        c = card(ident)
        _allowed(c, consumer)
        for name, part in (c.get("env") or {}).items():
            out[name] = _part(c, part, consumer)
    return out


def location(ident: str, part: str = "token") -> Path:
    """Where a file-kept grant lives — only for its own renewer or consent flow (e.g. writing a first OAuth token)."""
    scheme, where, _ = _split(card(ident)["secret"][part])
    if scheme != "file":
        raise GrantError(f"grant {ident}: {part} is not kept in a file")
    return _file(where)


def attribute(ident: str, storage_key: str, consumer: str | None = None) -> str:
    """A non-secret attribute stored next to a grant (e.g. a subscription's account id): declared in [attributes]."""
    c = card(ident)
    _allowed(c, consumer)
    storage = (c.get("attributes") or {}).get(storage_key)
    if not isinstance(storage, str):
        raise GrantError(f"grant {ident}: no attribute {storage_key!r}")
    return _static(c, "attribute:" + storage_key, storage, consumer)


# ── health (metadata only) ─────────────────────────────────────────────────────────────────────────────────
def _storage_health(storage: str) -> dict:
    scheme, where, key = _split(storage)
    if scheme == "external":
        return {"storage": "external", "where": where, "ok": True}
    if scheme == "file":
        p = _file(where)
        if not p.exists():
            return {"storage": "file", "ok": False, "problem": "missing"}
        mode = stat.S_IMODE(p.stat().st_mode)
        out = {"storage": "file", "ok": not mode & 0o077, "mode": oct(mode)}
        if mode & 0o077:
            out["problem"] = "readable by others"
        return out
    from .vault import VAULT
    try:
        item = VAULT.find(where)
    except Exception as exc:  # noqa: BLE001 — health reports, never raises
        return {"storage": "vault", "ok": False, "problem": type(exc).__name__}
    fields = VAULT.describe(item)["fields"]
    ok = key in fields or f"field:{key}" in fields
    return {"storage": "vault", "ok": ok, **({} if ok else {"problem": f"no field {key}"})}


def _expiry(c: dict) -> dict:
    try:
        if c["kind"] == "oauth":
            tok = json.loads(_file(_split(c["secret"]["token"])[1]).read_text())
            return {"refreshable": bool(tok.get("refresh_token")), "access_expires_in_s": int(tok.get("expires_at", 0) - time.time())}
        if c["kind"] == "subscription":
            if c.get("provider") == "anthropic-claude":
                path = _file(_split(c["secret"]["token"])[1])
                tok = json.loads(path.read_text()).get("claudeAiOauth") or {}
                return {"access_expires_in_s": int(tok.get("expiresAt", 0) / 1000 - time.time()),
                        "refreshable": bool(tok.get("refreshToken"))}
            tok = str(_read(c["secret"]["token"]) or "")
            return {"access_expires_in_s": int(_jwt_exp(tok) - time.time()) if tok else None}
    except Exception as exc:  # noqa: BLE001
        return {"expiry_problem": type(exc).__name__}
    return {}


def check(ident: str | None = None) -> dict:
    rows = []
    for c in ([card(ident)] if ident else cards()):
        storages = {k: _storage_health(v) for k, v in c["secret"].items()}
        storages.update({"attribute:" + k: _storage_health(v) for k, v in (c.get("attributes") or {}).items()})
        row = {k: c[k] for k in ("id", "title", "owner", "kind", "provider", "renewer", "consumers")}
        if c.get("allow") is not None:
            row["allow"] = c["allow"]
        if c.get("env"):
            row["env"] = sorted(c["env"])
        row["storage"] = storages
        row.update(_expiry(c))
        problems = [f"{k}: {s['problem']}" for k, s in storages.items() if not s["ok"]]
        if c["kind"] == "oauth" and row.get("refreshable") is False:
            problems.append("no refresh token")
        if c["kind"] == "subscription" and isinstance(row.get("access_expires_in_s"), int) and row["access_expires_in_s"] < 0 \
                and c["renewer"] == "none":
            problems.append("session expired")
        row["ok"], row["problems"] = not problems, problems
        rows.append(row)
    return {"ok": all(r["ok"] for r in rows), "grants": rows}

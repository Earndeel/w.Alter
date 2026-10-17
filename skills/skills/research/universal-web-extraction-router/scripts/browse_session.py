"""Walter Browse Session Manager (Lot 2).

First-class session abstraction for walter_browse. A session encapsulates
state (cookies, storage), engine affinity, identity, network scope and
lifecycle — without being coupled to Camoufox, Scrapling or any engine.

Key properties:
- ``network = local`` is ALWAYS the default. VPN/proxy routing is per-session
  and opt-in only; the global host network is never modified.
- Sessions are engine-agnostic: an engine (Camoufox Max context, HTTP replay,
  future personal CDP) is resolved per acquisition, never baked into the
  session object.
- Temporary sessions are destroyed on release/expiry; persistent sessions are
  saved by explicit ``save`` and never destroyed accidentally.
- No secret is ever logged: cookie values, tokens, headers and localStorage
  values stay out of traces. Only counts and identifiers appear.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from walter_paths import state_home as get_hermes_home


HOMES = {"/tmp", "/root/.camoufox-max-data"}

# --------------------------------------------------------------------------
# Public model
# --------------------------------------------------------------------------

IDENTITIES = {"anonymous", "personal", "temporary"}
NETWORK_MODES = {"local", "vpn", "proxy"}
KNOWN_COUNTRIES = {"FR", "US", "TH", "NL", "JP", "SG"}
SESSION_TTL_SECONDS = 30 * 60
STATE_FILENAME = "state.json"
STORAGE_FILENAME = "storage-state.json"
_COOKIE_KEYS = ("name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite")
_SENSITIVE_COOKIE_NAME = re.compile(r"(?i)(session|token|auth|secret|bearer|sid|csrf|xsrf|x-?api-?key)")


def _now() -> float:
    return time.time()


def _iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_host(domain: str) -> str:
    return (domain or "").lstrip(".").lower()


def cookies_for_domain(cookies: Sequence[Mapping[str, Any]], domain: str) -> list[dict[str, Any]]:
    """Return only the cookies whose domain matches ``domain`` (subdomain-safe).

    Used by HTTP replay so a session never leaks unrelated cookies into a
    request — only what the endpoint actually needs.
    """
    target = _safe_host(domain)
    result: list[dict[str, Any]] = []
    for cookie in cookies or []:
        cdomain = _safe_host(str(cookie.get("domain") or ""))
        if not cdomain:
            continue
        if cdomain == target or cdomain.endswith("." + target) or target.endswith("." + cdomain):
            result.append({k: cookie.get(k) for k in _COOKIE_KEYS if k in cookie})
    return result


def redact_cookies_for_log(cookies: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Describe cookies without values; flag sensitive names."""
    described: list[dict[str, Any]] = []
    for cookie in cookies or []:
        name = str(cookie.get("name") or "")
        described.append(
            {
                "name": name,
                "domain": cookie.get("domain"),
                "httpOnly": bool(cookie.get("httpOnly")),
                "secure": bool(cookie.get("secure")),
                "sensitive": bool(_SENSITIVE_COOKIE_NAME.search(name)),
            }
        )
    return described


# --------------------------------------------------------------------------
# Session object
# --------------------------------------------------------------------------

@dataclass
class BrowseSession:
    """A first-class Walter Browse session.

    Mutable identity/network fields are intended for acquisition-time
    configuration; state files and engine contexts are owned by the manager.
    """

    id: str
    identity: str = "anonymous"
    network: str = "local"
    country: str | None = None
    persistent: bool = False
    engine: str | None = None
    labels: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_iso)
    last_access: float = field(default_factory=_now)
    expires_at: float | None = None
    cookie_count: int = 0
    authenticated: bool = False
    storage_path: Path | None = None

    @property
    def authenticated_hint(self) -> bool:
        return self.authenticated

    def summary(self) -> dict[str, Any]:
        """Métadata only — never cookie values, tokens or storage content."""
        return {
            "id": self.id,
            "identity": self.identity,
            "network": self.network,
            "country": self.country,
            "persistent": self.persistent,
            "engine": self.engine,
            "cookie_count": self.cookie_count,
            "authenticated": self.authenticated,
            "created_at": self.created_at,
        }

# --------------------------------------------------------------------------
# Manager
# --------------------------------------------------------------------------

class SessionError(RuntimeError):
    pass


class SessionManager:
    """Create, load, acquire, save, destroy and expire sessions.

    Storage layout (per session, under the session root):
        <root>/<id>/state.json          — session metadata
        <root>/<id>/storage-state.json  — Playwright storageState payload
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else get_hermes_home() / "cache" / "walter-sessions"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._live: dict[str, BrowseSession] = {}

    def _session_dir(self, session_id: str) -> Path:
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
            raise SessionError("invalid session id")
        path = self.root / session_id
        if path.is_symlink() or path.resolve().parent != self.root.resolve():
            raise SessionError("session path escapes storage root")
        for name in (STATE_FILENAME, STORAGE_FILENAME):
            if (path / name).is_symlink():
                raise SessionError("session state must not be a symlink")
        return path

    # -- lifecycle ---------------------------------------------------------

    def create(
        self,
        *,
        identity: str = "anonymous",
        persistent: bool = False,
        country: str | None = None,
        network: str = "local",
        engine: str | None = None,
        ttl_seconds: float | None = SESSION_TTL_SECONDS,
        session_id: str | None = None,
    ) -> BrowseSession:
        if identity not in IDENTITIES and not identity.startswith("account:"):
            raise SessionError(f"unknown identity {identity!r}")
        if network not in NETWORK_MODES:
            raise SessionError(f"unknown network mode {network!r}")
        if country and country.upper() not in KNOWN_COUNTRIES:
            raise SessionError(f"unknown country {country!r}")
        sid = session_id or f"wb-{uuid.uuid4().hex[:12]}"
        with self._lock:
            if sid in self._live:
                raise SessionError(f"session {sid} is already live")
            session_dir = self._session_dir(sid)
            session_dir.mkdir(parents=True, exist_ok=True)
            session = BrowseSession(
                id=sid,
                identity=identity,
                network=network,
                country=country.upper() if country else None,
                persistent=persistent,
                engine=engine,
            )
            # RFC 1123-ish expiry; None for persistent sessions unless asked.
            session.expires_at = None if persistent else _now() + (ttl_seconds or SESSION_TTL_SECONDS)
            session.storage_path = session_dir / STORAGE_FILENAME
            self._live[sid] = session
        return session

    def load(self, session_id: str) -> BrowseSession:
        """Load a persisted session from disk (without warming any engine)."""
        session_dir = self._session_dir(session_id)
        state_path = session_dir / STATE_FILENAME
        if not state_path.exists():
            raise SessionError(f"persisted session {session_id} not found")
        payload = json.loads(state_path.read_text("utf-8"))
        session = BrowseSession(
            id=session_id,
            identity=str(payload.get("identity") or "anonymous"),
            network=str(payload.get("network") or "local"),
            country=payload.get("country"),
            persistent=bool(payload.get("persistent", True)),
            engine=payload.get("engine"),
            labels=list(payload.get("labels") or []),
            cookie_count=int(payload.get("cookie_count") or 0),
            authenticated=bool(payload.get("authenticated")),
        )
        session.storage_path = session_dir / STORAGE_FILENAME
        with self._lock:
            self._live[session_id] = session
        return session

    def get(self, session_id: str) -> BrowseSession:
        self._session_dir(session_id)
        with self._lock:
            if session_id in self._live:
                return self._live[session_id]
        if (self._session_dir(session_id) / STATE_FILENAME).exists():
            return self.load(session_id)
        raise SessionError(f"unknown session {session_id!r}")

    def clear_engine(self, session: BrowseSession) -> None:
        """Reset engine affinity after a failed acquire (avoids stale context)."""
        session.engine = None

    # -- persistence -------------------------------------------------------

    def save(self, session: BrowseSession, *, storage_state: Mapping[str, Any] | None = None) -> None:
        """Persist session metadata + cookies/storage. Explicit, scopéd, safe."""
        if not session.persistent:
            raise SessionError("refusing to persist a temporary session; make it persistent first")
        session_dir = self._session_dir(session.id)
        session_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "version": 1,
            "identity": session.identity,
            "network": session.network,
            "country": session.country,
            "persistent": session.persistent,
            "engine": session.engine,
            "labels": session.labels,
            "cookie_count": session.cookie_count,
            "authenticated": session.authenticated,
            "updated_at": _iso(),
        }
        with self._lock:
            (session_dir / STATE_FILENAME).write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
            if storage_state is not None:
                (session_dir / STORAGE_FILENAME).write_text(
                    json.dumps(storage_state, ensure_ascii=False), "utf-8"
                )

    def storage_state_path(self, session: BrowseSession) -> Path:
        return self._session_dir(session.id) / STORAGE_FILENAME

    # -- lifecycle ---------------------------------------------------------

    def destroy(self, session_id: str, *, include_disk: bool = True) -> None:
        """Force cleanup: drop live entry, engine hook, and (optionally) disk."""
        with self._lock:
            self._live.pop(session_id, None)
        session_dir = self._session_dir(session_id)
        if include_disk and session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)

    def expire_stale(self, *, now: float | None = None) -> list[str]:
        """Destroy expired temporary sessions (robust cleanup after errors)."""
        now = now or _now()
        expired: list[str] = []
        with self._lock:
            for sid, session in list(self._live.items()):
                if session.persistent or session.expires_at is None:
                    continue
                if session.expires_at < now:
                    expired.append(sid)
        for sid in expired:
            self.destroy(sid)
        return expired

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            live = [s.summary() for s in self._live.values()]
        persisted = []
        for child in sorted(self.root.iterdir()):
            try:
                self._session_dir(child.name)
            except SessionError:
                continue
            state = child / STATE_FILENAME
            if state.exists():
                try:
                    meta = json.loads(state.read_text("utf-8"))
                    persisted.append(
                        {
                            "id": child.name,
                            "identity": meta.get("identity"),
                            "network": meta.get("network"),
                            "country": meta.get("country"),
                            "cookie_count": meta.get("cookie_count") or 0,
                            "authenticated": meta.get("authenticated", False),
                        }
                    )
                except Exception:
                    continue
        # Deduplicate by id: a session appears once whether live, on disk, or both.
        by_id: dict[str, dict[str, Any]] = {}
        for entry in persisted + live:
            by_id[str(entry.get("id"))] = entry
        return list(by_id.values())

    # -- observability (NO secrets) ----------------------------------------

    def log_event(self, session: BrowseSession | None, event: str, **kwargs: Any) -> str:
        """Structured, redacted trace line."""
        parts = [f"{event}"]
        if session is not None:
            parts.append(f"id={session.id}")
            parts.append(f"identity={session.identity}")
            parts.append(f"network={session.network}")
            if session.country:
                parts.append(f"country={session.country}")
        for key, value in kwargs.items():
            if key.lower() in {"cookies", "values", "storage", "headers", "token"}:
                continue  # never serialize secrets
            parts.append(f"{key}={value}")
        line = " ".join(parts)
        return line

# --------------------------------------------------------------------------
# Migration helpers (old /tmp/cookies-*.json → session storage)
# --------------------------------------------------------------------------

def import_cookies_file(
    manager: SessionManager,
    path: str | Path,
    *,
    session_id: str,
    identity: str = "personal",
    persistent: bool = True,
) -> BrowseSession:
    """Import an existing cookies file (Playwright cookie list) into a session.

    The cookie VALUES are copied into the session's storage file (the same
    secrets the old system already held), but are never logged or echoed.
    """
    raw = json.loads(Path(path).read_text("utf-8"))
    cookies = raw if isinstance(raw, list) else raw.get("cookies", raw)
    if not isinstance(cookies, list):
        raise SessionError(f"unrecognized cookie file shape: {path}")
    session = manager.create(
        session_id=session_id,
        identity=identity,
        persistent=persistent,
        country=None,
        network="local",
    )
    storage_state = {"cookies": cookies, "origins": []}
    session.cookie_count = len(cookies)
    session.authenticated = len(cookies) > 0
    manager.save(session, storage_state=storage_state)
    return session
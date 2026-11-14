"""Value-free fingerprints of the vault's secret values, so other modules can mask them without ever holding them.

walter-logs (and the core.events write door) must mask a credential even when nothing in its shape says it is one
(2026-10-30: a bare 32-hex Kie key pasted in a Claude Code chat was written in clear to walter_logs). The index holds,
for every secret value of the owner's Bitwarden, only HMAC-SHA256(local key, value) truncated to 128 bits, plus the
set of value lengths. The key is a random local file (0600): without it the index cannot be tested offline against a
dictionary of weak passwords.

  build()                  read the whole vault (shared bw session), write the index; called by secrets_sync watch
                           on every vault revision, or `walter-secret fingerprints build`
  status()                 counts and age, never a value
  scrub(text)              text with every known vault value replaced by «secret:vault» (fail-open when no index)

Indexed: login password and TOTP seed, every text/hidden custom field, card number and code, identity numbers.
Skipped: values with whitespace, shorter than 8, short single-class values (8–11 chars, letters only or digits
only), e-mail addresses, URLs, booleans. Notes are not indexed (free text).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets as _random
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import settings

KEY_FILE = settings.path("fingerprint_key", "@instance/state/secrets/fingerprint.key")
INDEX_FILE = settings.path("fingerprints", "@instance/state/secrets/fingerprints.json")
MASK = "«secret:vault»"
MIN_LEN = 8
_TOKEN = re.compile(r"[^\s'\"`<>()\[\]{}|,;\\]+")
_SPLIT = "=:&?/@#"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
_RELOAD_S = 30


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def _key(create: bool = False) -> bytes | None:
    try:
        return KEY_FILE.read_bytes()
    except OSError:
        if not create:
            return None
    key = _random.token_bytes(32)
    _write_private(KEY_FILE, key)
    return key


def _digest(key: bytes, value: str) -> str:
    return hmac.digest(key, value.encode(), "sha256")[:16].hex()


def worth_indexing(value) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    if len(v) < MIN_LEN or any(c.isspace() for c in v) or v.lower() in ("true", "false", "null", "none"):
        return False
    if _EMAIL.match(v) or re.match(r"^[a-z][a-z0-9+.-]*://", v, re.I):
        return False
    classes = sum(bool(re.search(rx, v)) for rx in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]"))
    return len(v) >= 12 or classes >= 2


def secret_values(item: dict) -> list[str]:
    """The values of one Bitwarden item that are secrets (see module doc)."""
    out = []
    login = item.get("login") or {}
    out += [login.get("password"), login.get("totp")]
    out += [f.get("value") for f in item.get("fields") or [] if f.get("type") in (0, 1)]
    card = item.get("card") or {}
    out += [card.get("number"), card.get("code")]
    ident = item.get("identity") or {}
    out += [ident.get("ssn"), ident.get("passportNumber"), ident.get("licenseNumber")]
    return [v.strip() for v in out if worth_indexing(v)]


def build() -> dict:
    """Fingerprint every secret value of the vault (one `bw list items`, shared session)."""
    from .secrets_sync import bw
    bw("sync")
    items = json.loads(bw("list", "items"))
    key = _key(create=True)
    digests, lengths = set(), set()
    for item in items:
        for v in secret_values(item):
            digests.add(_digest(key, v))
            lengths.add(len(v))
    index = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": len(items),
             "values": len(digests), "lengths": sorted(lengths), "digests": sorted(digests)}
    _write_private(INDEX_FILE, json.dumps(index).encode())
    _matcher.reset()
    return status()


def status() -> dict:
    try:
        idx = json.loads(INDEX_FILE.read_text())
    except (OSError, ValueError):
        return {"ok": False, "index": str(INDEX_FILE), "error": "no index (walter-secret fingerprints build)"}
    return {"ok": True, "index": str(INDEX_FILE), "built_at": idx.get("built_at"), "items": idx.get("items"),
            "values": idx.get("values")}


class _Matcher:
    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self._checked, self._mtime, self._key, self._lengths, self._digests = 0.0, None, None, frozenset(), frozenset()

    def _load(self) -> bool:
        now = time.monotonic()
        with self._lock:
            if now - self._checked >= _RELOAD_S:
                self._checked = now
                try:
                    mtime = INDEX_FILE.stat().st_mtime
                    if mtime != self._mtime:
                        idx = json.loads(INDEX_FILE.read_text())
                        key = _key()
                        if key:
                            self._key, self._mtime = key, mtime
                            self._lengths, self._digests = frozenset(idx["lengths"]), frozenset(idx["digests"])
                except (OSError, ValueError, KeyError):
                    pass
            return bool(self._key and self._digests)

    def _hit(self, tok: str) -> bool:
        return len(tok) in self._lengths and _digest(self._key, tok) in self._digests

    def _token(self, tok: str) -> str:
        if len(tok) < MIN_LEN:
            return tok
        if self._hit(tok):
            return MASK
        for sep in _SPLIT:                          # KEY=value, user:pass, ?key=value&…, a/b
            if sep in tok:
                return sep.join(self._token(part) for part in tok.split(sep))
        return tok

    def scrub(self, text):
        if not text or not isinstance(text, str) or not self._load():
            return text
        return _TOKEN.sub(lambda m: self._token(m.group()), text)


_matcher = _Matcher()


def scrub(text):
    """Every known vault value in `text` replaced by «secret:vault». Without an index, the text is unchanged."""
    return _matcher.scrub(text)

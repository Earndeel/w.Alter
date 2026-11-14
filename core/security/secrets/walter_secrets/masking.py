"""Runtime-neutral redaction. Only registered values; no dependency on Hermes.

Redaction protects accidental echoes, not arbitrary encodings by untrusted code.
For a secret-bearing child process, discard its output instead of relying on it.
"""
from __future__ import annotations
import base64
import json
import threading
import time
from urllib.parse import quote, quote_plus


class Masker:
    def __init__(self, source=None, *, ttl: float = 600):
        self.source = source
        self.ttl = ttl
        self._loaded_at = float('-inf')
        self._cached = {}
        self._registered = {}
        self._lock = threading.RLock()

    def register(self, value: str, replacement: str = '[secret]') -> None:
        if not isinstance(value, str) or not value:
            return
        variants = {value, quote(value, safe=''), quote_plus(value), json.dumps(value)[1:-1]}
        # Include common accidental transport encodings. This is not a complete information-flow boundary.
        if len(value) >= 8:
            variants.add(base64.b64encode(value.encode()).decode())
        with self._lock:
            self._registered.update({v: replacement for v in variants if v and v != replacement})

    def table(self) -> dict[str, str]:
        with self._lock:
            if self.source and time.monotonic() - self._loaded_at >= self.ttl:
                try:
                    fresh = self.source()
                    self._cached = {k: v for k, v in fresh.items() if isinstance(k, str) and k}
                    self._loaded_at = time.monotonic()
                except Exception:
                    # A lookup failure never discards previously-known or explicitly-used values.
                    self._loaded_at = time.monotonic() - max(0, self.ttl - 60)
            return {**self._cached, **self._registered}

    def scrub(self, value: str) -> str:
        if not isinstance(value, str) or not value:
            return value
        for secret, replacement in sorted(self.table().items(), key=lambda pair: -len(pair[0])):
            value = value.replace(secret, replacement)
        return value

    def walk(self, value):
        if isinstance(value, str):
            return self.scrub(value)
        if isinstance(value, list):
            return [self.walk(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.walk(item) for item in value)
        if isinstance(value, dict):
            return {self.scrub(k) if isinstance(k, str) else k: self.walk(v) for k, v in value.items()}
        return value


def public_error(exc: BaseException, *, operation: str = 'secret operation') -> dict:
    """Do not echo exceptions from secret-bearing subprocesses, URLs, arguments or results."""
    # Exception names/types are implementation controlled; their messages may contain credentials.
    category = 'invalid_request' if isinstance(exc, (ValueError, TypeError, KeyError)) else 'operation_failed'
    return {'error': category, 'message': f'{operation} failed; sensitive diagnostics suppressed'}

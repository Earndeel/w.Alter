"""Result cache (Lot 3 — DATA plane).

Strictly separate from the knowledge plane (ProfileIndex/capabilities):
- KNOWLEDGE = how to fetch (kept for a long time, in profiles.json)
- DATA     = what was fetched (short-lived, in result_cache.json)

Every entry carries source, timestamp, content hash, TTL, request params,
capability used, and a freshness verdict. The caller decides whether a stale
entry is usable (recipes are reused, data is re-fetched for dynamic content).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

try:  # Hermes runtime; isolated venv falls back to HOME/.hermes
    from hermes_constants import get_hermes_home
except ImportError:  # pragma: no cover
    def get_hermes_home() -> Path:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


try:  # pragma: no cover - fcntl is present on supported Linux/macOS runtimes
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


DEFAULT_TTL_SECONDS = 300  # 5 min default: conservative for dynamic-ish data
_MAX_ENTRIES = 1000
# Refuse to cache these knowledge bits (they are knowledge, not data), and
# mark dynamic-result TTLs as very short so recipes are reused but data is fresh.
DYNAMIC_GOAL_MARKERS = ("price", "stock", "availability", "hotel", "flight", "sport", "live", "status")

_REDACTED = "<redacted>"


def default_cache_path() -> Path:
    return get_hermes_home() / "cache" / "universal-web-extraction" / "result_cache.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class ResultCache:
    """Small, locked, JSON-backed cache for extraction results (data only)."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        default_ttl_seconds: float = DEFAULT_TTL_SECONDS,
        dynamic_ttl_seconds: float = 60.0,
        max_entries: int = _MAX_ENTRIES,
    ) -> None:
        self.path = Path(path) if path is not None else default_cache_path()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.default_ttl = max(0.0, float(default_ttl_seconds))
        self.dynamic_ttl = max(0.0, float(dynamic_ttl_seconds))
        self.max_entries = max(1, int(max_entries))
        self._thread_lock = threading.RLock()

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "updated_at": _utc_now(), "entries": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            entries = payload.get("entries") if isinstance(payload, Mapping) else None
            return {
                "version": 1,
                "updated_at": str(payload.get("updated_at") or _utc_now()),
                "entries": {str(k): dict(v) for k, v in (entries or {}).items() if isinstance(v, Mapping)},
            }
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return {"version": 1, "updated_at": _utc_now(), "entries": {}, "load_error": str(exc)[:300]}

    def _write_unlocked(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    @staticmethod
    def entry_key(host: str, capability: str, params: Mapping[str, Any] | None = None) -> str:
        identity = {"host": host, "capability": capability, "params": dict(params or {})}
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def content_hash(records: Any) -> str:
        encoded = json.dumps(records, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

    def _ttl_for(self, capability: str, explicit_ttl: float | None) -> float:
        if explicit_ttl is not None:
            return max(0.0, float(explicit_ttl))
        lowered = capability.lower()
        if any(marker in lowered for marker in DYNAMIC_GOAL_MARKERS):
            return self.dynamic_ttl
        return self.default_ttl

    def put(
        self,
        *,
        host: str,
        capability: str,
        params: Mapping[str, Any] | None,
        records: list[dict[str, Any]],
        source_url: str,
        route: str,
        ttl_seconds: float | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> str:
        """Store fetched data. Only lightweight serializable values are kept."""
        key = self.entry_key(host, capability, params)
        now = time.time()
        ttl = self._ttl_for(capability, ttl_seconds)
        entry = {
            "key": key,
            "host": host,
            "capability": capability,
            "params": dict(params or {}),
            "fetched_at": _utc_now(),
            "fetched_epoch": now,
            "expires_epoch": now + ttl,
            "ttl_seconds": ttl,
            "source_url": source_url,
            "route": route,
            "content_hash": self.content_hash(records),
            "record_count": len(records),
            "records": [dict(record) for record in records if isinstance(record, Mapping)],
        }
        if extra:
            entry.update({str(k): v for k, v in extra.items() if k not in entry})
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            entries = payload["entries"]
            entries[key] = entry
            if len(entries) > self.max_entries:
                oldest = sorted(entries.values(), key=lambda e: _safe_float(e.get("fetched_epoch"), 0.0))
                for stale in oldest[: len(entries) - self.max_entries]:
                    entries.pop(stale.get("key"), None)
            payload["version"] = 1
            payload["updated_at"] = _utc_now()
            self._write_unlocked(payload)
        return key

    def get(self, host: str, capability: str, params: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
        """Return the cache entry (records NOT inlined) plus freshness verdict.

        The caller decides if a stale entry is usable; fresh entries have
        ``fresh=True``.
        """
        key = self.entry_key(host, capability, params)
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            entry = payload["entries"].get(key)
            if entry is None:
                return None
            entry = dict(entry)
            now = time.time()
            entry["fresh"] = _safe_float(entry.get("expires_epoch"), 0.0) >= now
            entry["age_s"] = round(max(0.0, now - _safe_float(entry.get("fetched_epoch"), now)), 1)
        return entry

    def invalidate(self, host: str, capability: str, params: Mapping[str, Any] | None = None) -> bool:
        key = self.entry_key(host, capability, params)
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            if key not in payload["entries"]:
                return False
            del payload["entries"][key]
            payload["updated_at"] = _utc_now()
            self._write_unlocked(payload)
            return True

    def stats(self) -> dict[str, Any]:
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            entries = payload["entries"]
            now = time.time()
            return {
                "path": str(self.path),
                "entry_count": len(entries),
                "fresh_count": sum(
                    _safe_float(e.get("expires_epoch"), 0.0) >= now for e in entries.values()
                ),
                "updated_at": payload.get("updated_at"),
            }

    def clear(self) -> None:
        with self._thread_lock, self._file_lock():
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


# Legacy import alias (migration path): the cache was previously known as
# `web_cache` in design notes; keep the canonical name only.
WebCache = ResultCache  # noqa: N816 — backward-compatible alias
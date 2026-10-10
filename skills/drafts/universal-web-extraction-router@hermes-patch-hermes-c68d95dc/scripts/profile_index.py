from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from universal_extractor import ExtractionResult, ExtractionSpec, result_shape_fingerprint

try:  # Hermes is available in the normal runtime, not in the isolated Scrapling venv.
    from hermes_constants import get_hermes_home
except ImportError:  # pragma: no cover - exercised by the standalone venv
    def get_hermes_home() -> Path:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


INDEX_VERSION = 4
DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
DEFAULT_MAX_PROFILES = 500
DEFAULT_MAX_CAPABILITIES = 200
_MAX_CAPABILITY_VERSIONS = 3
_PROMOTE_MIN_SUCCESSES = 2
_CAPABILITY_OPERATION_RE = re.compile(
    r"(search|find|list|lookup|detail|availability|invoice|transaction|posts|products|flight|hotel|price|status)",
    re.IGNORECASE,
)
_ROUTE_NAMES = {"replay", "scrapling", "camoufox-max", "webtop-cdp", "api-replay", "static-html"}
_DYNAMIC_PATH_SEGMENT = re.compile(r"^(?:\d{3,}|[0-9a-f]{8,}|[0-9a-f-]{16,})$", re.IGNORECASE)
_SENSITIVE_QUERY_KEY = re.compile(
    r"(?:token|secret|password|passwd|authorization|cookie|session|csrf|signature|sig|api[_-]?key|access[_-]?key|private)",
    re.IGNORECASE,
)
_LIKELY_DYNAMIC_QUERY_KEY = re.compile(
    r"(?:date|day|origin|dest|city|airport|query|search|term|page|cursor|sort|filter|adult|child|room|hotel|id|limit|\bq\b)",
    re.IGNORECASE,
)
_UNSAFE_STATIC_VALUE = re.compile(r"^[A-Za-z0-9_-]{48,}$")

try:  # pragma: no cover - fcntl is present on the supported Linux/macOS runtimes
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback keeps thread safety
    fcntl = None  # type: ignore[assignment]


class ProfileIndexError(RuntimeError):
    """Raised when an invalid profile-index operation is requested."""


def default_index_path() -> Path:
    """Return the profile index path for the active Hermes profile."""
    return get_hermes_home() / "cache" / "universal-web-extraction" / "profiles.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalized_host(url: str) -> str:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower().strip(".")
    if not hostname:
        return ""
    if hostname.startswith("www."):
        hostname = hostname[4:]
    port = parsed.port
    if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        return f"{hostname}:{port}"
    return hostname


def _normalized_path(path: str) -> str:
    raw_segments = [segment for segment in path.split("/") if segment]
    segments = ["{id}" if _DYNAMIC_PATH_SEGMENT.fullmatch(segment) else segment.lower() for segment in raw_segments]
    return "/" + "/".join(segments) if segments else "/"


def url_scope(url: str) -> dict[str, Any]:
    """Reduce a URL to a reusable, value-free site/route identity.

    Query values are intentionally discarded so dates, prices, search terms and
    pagination do not create one profile per request. Query *names* remain part
    of the scope because they often distinguish two different site journeys.
    """
    parsed = urlsplit(url)
    query_keys = sorted({key for key, _ in parse_qsl(parsed.query, keep_blank_values=True) if key})
    host = _normalized_host(url)
    path = _normalized_path(parsed.path)
    return {
        "host": host,
        "path": path,
        "query_keys": query_keys,
        "scope": urlunsplit(("", host, path, "&".join(query_keys), "")),
    }


def spec_signature(spec: ExtractionSpec) -> dict[str, Any]:
    """Return the stable semantic contract used to distinguish journeys."""
    return {
        "name": spec.name,
        "expected_fields": {
            str(key): sorted(str(alias) for alias in aliases)
            for key, aliases in sorted(spec.expected_fields.items())
        },
        "required_fields": sorted(str(field) for field in spec.required_fields),
        "min_records": spec.min_records,
        "score_threshold": spec.score_threshold,
        "dom_profile": spec.dom_profile,
        "replay_query_keys": sorted(str(key) for key in spec.replay_query_keys),
    }


def spec_fingerprint(spec: ExtractionSpec) -> str:
    encoded = json.dumps(spec_signature(spec), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _same_site(left: str, right: str) -> bool:
    return left == right or left.endswith(f".{right}") or right.endswith(f".{left}")


def _safe_static_value(key: str, value: str) -> bool:
    if _SENSITIVE_QUERY_KEY.search(key):
        return False
    if len(value) > 128 or any(ord(char) < 32 for char in value):
        return False
    return not _UNSAFE_STATIC_VALUE.fullmatch(value)


def build_replay_template(
    source_url: str,
    candidate_url: str,
    *,
    method: str,
    content_type: str,
    dynamic_query_keys: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    """Build a value-safe template for a same-site GET JSON response."""
    source = urlsplit(source_url)
    candidate = urlsplit(candidate_url)
    source_host = _normalized_host(source_url)
    candidate_host = _normalized_host(candidate_url)
    if (
        method.upper() != "GET"
        or "json" not in content_type.lower()
        or source.scheme not in {"http", "https"}
        or candidate.scheme not in {"http", "https"}
        or not source_host
        or not candidate_host
        or not _same_site(source_host, candidate_host)
        or candidate.username is not None
        or candidate.password is not None
        or any(_DYNAMIC_PATH_SEGMENT.fullmatch(segment) for segment in candidate.path.split("/") if segment)
    ):
        return None

    source_pairs = parse_qsl(source.query, keep_blank_values=True)
    source_by_key: dict[str, str] = {}
    for key, value in source_pairs:
        source_by_key.setdefault(key, value)
    dynamic_keys = {key.lower() for key in dynamic_query_keys}
    query: list[dict[str, str]] = []
    for key, value in parse_qsl(candidate.query, keep_blank_values=True):
        if _SENSITIVE_QUERY_KEY.search(key):
            return None
        if key in source_by_key:
            query.append({"name": key, "source_key": key})
            continue
        matching_source_key = None
        if _LIKELY_DYNAMIC_QUERY_KEY.search(key):
            matching_source_key = next(
                (
                    source_key
                    for source_key, source_value in source_pairs
                    if source_value == value and not _SENSITIVE_QUERY_KEY.search(source_key)
                ),
                None,
            )
        if matching_source_key is not None:
            query.append({"name": key, "source_key": matching_source_key})
            continue
        if key.lower() in dynamic_keys:
            return None
        if not _safe_static_value(key, value):
            return None
        query.append({"name": key, "value": value})

    return {
        "version": 1,
        "method": "GET",
        "scheme": candidate.scheme,
        "host": candidate.netloc.lower(),
        "path": candidate.path or "/",
        "source_host": source_host,
        "query": query,
    }


def render_replay_url(template: Mapping[str, Any], source_url: str) -> str:
    """Render a learned template against the current source URL parameters."""
    source = urlsplit(source_url)
    source_host = _normalized_host(source_url)
    template_source_host = str(template.get("source_host") or "")
    if not source_host or not template_source_host or not _same_site(source_host, template_source_host):
        raise ValueError("replay source is outside the learned site scope")
    source_values: dict[str, str] = {}
    for key, value in parse_qsl(source.query, keep_blank_values=True):
        source_values.setdefault(key, value)
    query: list[tuple[str, str]] = []
    for item in template.get("query", []):
        if not isinstance(item, Mapping):
            raise ValueError("invalid replay query item")
        name = str(item.get("name") or "")
        if not name:
            raise ValueError("replay query item has no name")
        if "source_key" in item:
            source_key = str(item.get("source_key") or "")
            if source_key not in source_values:
                raise ValueError(f"missing replay parameter: {source_key}")
            query.append((name, source_values[source_key]))
        else:
            query.append((name, str(item.get("value") or "")))
    return urlunsplit(
        (
            str(template.get("scheme") or "https"),
            str(template.get("host") or ""),
            str(template.get("path") or "/"),
            urlencode(query),
            "",
        )
    )


def profile_key(url: str, spec: ExtractionSpec) -> str:
    scope = url_scope(url)
    identity = {
        "host": scope["host"],
        "path": scope["path"],
        "query_keys": scope["query_keys"],
        "spec": spec_fingerprint(spec),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


def _candidate_descriptor(
    source_url: str,
    spec: ExtractionSpec,
    result: ExtractionResult,
) -> dict[str, Any] | None:
    candidate = result.best_candidate
    if candidate is None:
        return None
    candidate_scope = url_scope(candidate.url)
    first_record = result.records[0] if result.records else {}
    field_paths = {
        key.removeprefix("_").removesuffix("_path"): value
        for key, value in first_record.items()
        if key.startswith("_")
        and key.endswith("_path")
        and key != "_source_path"
        and isinstance(value, str)
    }
    replay_template = build_replay_template(
        source_url,
        candidate.url,
        method=candidate.method,
        content_type=candidate.content_type,
        dynamic_query_keys=spec.replay_query_keys,
    )
    return {
        "source": "dom" if candidate.method == "DOM" else "network",
        "host": candidate_scope["host"],
        "path": candidate_scope["path"],
        "query_keys": candidate_scope["query_keys"],
        "method": candidate.method,
        "content_type": candidate.content_type[:100],
        "matched_fields": list(candidate.matched_fields),
        "source_path": first_record.get("_source_path", ""),
        "field_paths": field_paths,
        "request_body_bytes": candidate.request_body_bytes,
        "request_body_sha256": candidate.request_body_sha256,
        "shape_fingerprint": result_shape_fingerprint(result),
        "replay_template": replay_template,
    }


def _route_stats(entry: dict[str, Any], route: str) -> dict[str, int]:
    stats = entry.setdefault("route_stats", {}).setdefault(route, {})
    stats.setdefault("attempts", 0)
    stats.setdefault("successes", 0)
    stats.setdefault("failures", 0)
    return stats


# --------------------------------------------------------------------------
# Lot 3 — Domain profiles and capability registry
# --------------------------------------------------------------------------

def capability_name_from_spec(spec: ExtractionSpec, scope: Mapping[str, Any]) -> str:
    """Infer a reusable capability name from the spec/scope, or None.

    Heuristic, deterministic, zero LLM: operation-like spec names or
    path tokens win; generic page fetches produce no capability.
    """
    name = (spec.name or "").strip().lower()
    if name:
        candidate = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
        if candidate and _CAPABILITY_OPERATION_RE.search(candidate):
            return candidate[:48]
    for token in (scope.get("path") or "").strip("/").split("/"):
        if _CAPABILITY_OPERATION_RE.search(token):
            return token[:48]
    return ""


def _fresh_confidence(
    *,
    base: float,
    successes: int,
    failures: int,
    last_verified_epoch: float,
    now_epoch: float,
    freshness_window: float = 14 * 24 * 3600,
) -> float:
    """Confidence in [0, 1]: base + success evidence - failure evidence,
    decaying with age past the freshness window."""
    confidence = base + 0.06 * min(successes, 20) - 0.10 * min(failures, 10)
    confidence = max(0.05, min(0.99, confidence))
    age = max(0.0, now_epoch - last_verified_epoch)
    if age > freshness_window:
        confidence *= max(0.35, 1.0 - (age - freshness_window) / (30 * 24 * 3600))
    return round(confidence, 3)


def parameterize_url_slots(url: str, *, dynamic_keys: Sequence[str] | None = None) -> str:
    """Turn dynamic query values into {{key}} slots for capability recipes.

    Query keys listed in ``dynamic_keys`` (or matching the likely-dynamic
    pattern) become templated slots; sensitive values are discarded. This
    lets a learned journey be replayed with new inputs instead of frozen
    values. Unknown/static pairs are kept as-is.
    """
    parsed = urlsplit(url)
    dynamic = dynamic_keys or ()
    dynamic_set = {str(k).lower() for k in dynamic}
    query: list[str] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if _SENSITIVE_QUERY_KEY.search(key):
            continue  # never store or replay secrets
        if lowered in dynamic_set or _LIKELY_DYNAMIC_QUERY_KEY.search(key):
            query.append(f"{key}={{{{{key}}}}}")
        elif _safe_static_value(key, value):
            query.append(f"{key}={value}")
        # else: unsafe/static-looking value dropped from the recipe
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "&".join(query), ""))


def _new_domain_profile(host: str) -> dict[str, Any]:
    return {
        "host": host,
        "first_seen_at": _utc_now(),
        "last_verified_at": _utc_now(),
        "last_verified_epoch": time.time(),
        "successes": 0,
        "failures": 0,
        "routing": {"preferred": None, "confidence": 0.0},
        "behavior": {"requires_js": False, "geo_sensitive": False, "challenge_seen": False},
        "endpoints": [],
        "capabilities": [],
        "average_latency_ms": 0.0,
        "latency_samples": 0,
    }


def _new_capability(
    host: str,
    name: str,
    *,
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
    implementation: Mapping[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    now_iso = created_at or _utc_now()
    return {
        "host": host,
        "name": name,
        "version": 1,
        "versions": [{"version": 1, "created_at": now_iso, "notes": "initial"}],
        "inputs": dict(inputs),
        "outputs": dict(outputs),
        "implementation": dict(implementation),
        "successes": 0,
        "failures": 0,
        "confidence": 0.5,
        "last_verified_at": now_iso,
        "last_verified_epoch": time.time(),
        "status": "proposed",  # proposed -> active -> degraded/invalidated
        "last_latency_ms": None,
        "average_latency_ms": 0.0,
        "latency_samples": 0,
    }


def _update_schema_state(
    entry: dict[str, Any],
    candidate: Mapping[str, Any],
    *,
    route: str,
) -> None:
    current_shape = str(candidate.get("shape_fingerprint") or "")
    if not current_shape:
        return
    baseline = str(entry.get("shape_fingerprint") or "")
    if not baseline:
        entry.update(
            {
                "shape_fingerprint": current_shape,
                "last_observed_shape": current_shape,
                "schema_status": "stable",
                "schema_drift_streak": 0,
                "schema_drift_count": 0,
                "replay_enabled": bool(candidate.get("replay_template")),
                "replay_reenable_streak": 0,
            }
        )
        return

    if current_shape == baseline:
        entry.update(
            {
                "last_observed_shape": current_shape,
                "schema_status": "stable",
                "schema_drift_streak": 0,
            }
        )
        if route != "replay" and candidate.get("replay_template"):
            reenable_streak = _safe_int(entry.get("replay_reenable_streak")) + 1
            entry["replay_reenable_streak"] = reenable_streak
            if reenable_streak >= 2:
                entry["replay_enabled"] = True
        return

    previous_observation = str(entry.get("last_observed_shape") or "")
    drift_streak = _safe_int(entry.get("schema_drift_streak")) + 1 if previous_observation == current_shape else 1
    entry.update(
        {
            "last_observed_shape": current_shape,
            "schema_drift_streak": drift_streak,
            "schema_status": "drifted" if drift_streak >= 2 else "suspected",
            "replay_enabled": False,
            "replay_reenable_streak": 0,
        }
    )
    if drift_streak >= 2:
        entry.update(
            {
                "previous_shape_fingerprint": baseline,
                "shape_fingerprint": current_shape,
                "schema_drift_count": _safe_int(entry.get("schema_drift_count")) + 1,
                "last_schema_drift_at": _utc_now(),
            }
        )


class ProfileHit:
    """A lookup result; a stale hit is diagnostic but never a route shortcut."""

    def __init__(
        self,
        *,
        key: str,
        entry: Mapping[str, Any],
        match: str,
        now: float,
        ttl_seconds: float,
        max_age_seconds: float,
    ) -> None:
        self.key = key
        self.entry = dict(entry)
        self.match = match
        age = max(0.0, now - _safe_float(entry.get("last_success_epoch"), now))
        self.age_seconds = age
        self.fresh = age <= ttl_seconds
        self.expired = age > max_age_seconds
        status = str(entry.get("status") or "active")
        self.prefer = self.fresh and not self.expired and status == "active" and _safe_int(entry.get("failure_streak")) < 2

    @property
    def preferred_route(self) -> str | None:
        if self.replay_available:
            # A validated API discovery is the fastest re-entry: the learned
            # replay template targets the JSON endpoint directly (downgrade).
            if self.entry.get("api_replay_validated") is True:
                return "api-replay"
            return "replay"
        route = self.entry.get("preferred_route")
        return str(route) if self.prefer and route in _ROUTE_NAMES else None

    @property
    def replay_available(self) -> bool:
        return bool(
            self.prefer
            and self.entry.get("replay_enabled", True)
            and isinstance(self.entry.get("replay_template"), Mapping)
        )

    def summary(self) -> dict[str, Any]:
        return {
            "hit": True,
            "key": self.key,
            "match": self.match,
            "host": self.entry.get("host", ""),
            "path": self.entry.get("path", ""),
            "scenario": self.entry.get("scenario", ""),
            "preferred_route": self.preferred_route,
            "stored_route": self.entry.get("preferred_route"),
            "fresh": self.fresh,
            "stale": not self.fresh,
            "expired": self.expired,
            "status": self.entry.get("status", "active"),
            "age_s": round(self.age_seconds, 1),
            "success_count": _safe_int(self.entry.get("success_count")),
            "failure_streak": _safe_int(self.entry.get("failure_streak")),
            "last_record_count": _safe_int(self.entry.get("last_record_count")),
            "replay_available": self.replay_available,
            "replay_path": (
                self.entry.get("replay_template", {}).get("path")
                if isinstance(self.entry.get("replay_template"), Mapping)
                else None
            ),
            "schema_status": self.entry.get("schema_status", "unknown"),
            "schema_drift_streak": _safe_int(self.entry.get("schema_drift_streak")),
            "schema_drift_count": _safe_int(self.entry.get("schema_drift_count")),
        }


class ProfileIndex:
    """Small persistent registry of validated site/route extraction profiles.

    The registry stores route knowledge, not scraped data. It is deliberately a
    hint layer: every returned result still passes the shared semantic contract,
    and a failed hint is demoted so the universal fallback chain can recover.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
        max_profiles: int = DEFAULT_MAX_PROFILES,
    ) -> None:
        self.path = Path(path) if path is not None else default_index_path()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self.max_age_seconds = max(self.ttl_seconds, float(max_age_seconds))
        self.max_profiles = max(1, int(max_profiles))
        self._thread_lock = threading.RLock()
        self._load_error: str | None = None

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
        self._load_error = None
        empty = {
            "version": INDEX_VERSION,
            "updated_at": _utc_now(),
            "profiles": {},
            "domains": {},
            "capabilities": {},
        }
        if not self.path.exists():
            return empty
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            profiles = payload.get("profiles") if isinstance(payload, Mapping) else None
            if not isinstance(profiles, Mapping):
                raise ValueError("profiles must be an object")
            domains = payload.get("domains") if isinstance(payload, Mapping) else None
            capabilities = payload.get("capabilities") if isinstance(payload, Mapping) else None
            return {
                "version": _safe_int(payload.get("version"), INDEX_VERSION),
                "updated_at": str(payload.get("updated_at") or _utc_now()),
                "profiles": {str(key): dict(value) for key, value in profiles.items() if isinstance(value, Mapping)},
                "domains": {str(key): dict(value) for key, value in (domains or {}).items() if isinstance(value, Mapping)},
                "capabilities": {
                    str(key): dict(value) for key, value in (capabilities or {}).items() if isinstance(value, Mapping)
                },
            }
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self._load_error = f"{type(exc).__name__}: {exc}"[:300]
            return empty

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

    def _prune_unlocked(self, profiles: dict[str, Any]) -> None:
        if len(profiles) <= self.max_profiles:
            return
        ordered = sorted(
            profiles.items(),
            key=lambda item: _safe_float(item[1].get("last_success_epoch"), 0.0),
            reverse=True,
        )
        profiles.clear()
        profiles.update(ordered[: self.max_profiles])

    @staticmethod
    def _find_entry_unlocked(
        profiles: Mapping[str, Any],
        exact_key: str,
        scope: Mapping[str, Any],
        schema_fingerprint: str,
    ) -> tuple[str, dict[str, Any] | None]:
        exact = profiles.get(exact_key)
        if isinstance(exact, Mapping):
            return exact_key, dict(exact)
        candidates = [
            (candidate_key, candidate)
            for candidate_key, candidate in profiles.items()
            if isinstance(candidate, Mapping)
            and candidate.get("host") == scope["host"]
            and candidate.get("path") == scope["path"]
            and candidate.get("spec_fingerprint") == schema_fingerprint
        ]
        if not candidates:
            return exact_key, None
        key, entry = max(
            candidates,
            key=lambda item: _safe_float(item[1].get("last_success_epoch"), 0.0),
        )
        return key, dict(entry)

    def lookup(self, url: str, spec: ExtractionSpec) -> ProfileHit | None:
        scope = url_scope(url)
        key = profile_key(url, spec)
        with self._thread_lock, self._file_lock():
            profiles = self._load_unlocked()["profiles"]
            key, entry = self._find_entry_unlocked(
                profiles,
                key,
                scope,
                spec_fingerprint(spec),
            )
            if entry is None:
                return None
            return ProfileHit(
                key=key,
                entry=entry,
                match="exact" if key == profile_key(url, spec) else "path",
                now=time.time(),
                ttl_seconds=self.ttl_seconds,
                max_age_seconds=self.max_age_seconds,
            )

    def observe(
        self,
        url: str,
        spec: ExtractionSpec,
        *,
        route: str,
        result: ExtractionResult,
        attempts: list[Mapping[str, Any]] | None = None,
        api_discovered: bool = False,
        api_replay_validated: bool | None = None,
        endpoint_contract: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist one completed route observation without storing response data."""
        if route not in _ROUTE_NAMES:
            raise ProfileIndexError(f"unknown route: {route}")
        usable = bool(result.valid_candidate_count and result.records)
        key = profile_key(url, spec)
        scope = url_scope(url)
        now_epoch = time.time()
        now_iso = _utc_now()
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            profiles = payload["profiles"]
            key, existing_entry = self._find_entry_unlocked(
                profiles,
                key,
                scope,
                spec_fingerprint(spec),
            )
            entry = profiles.get(key)
            if entry is None and existing_entry is not None:
                entry = existing_entry
            if entry is None and not usable:
                # Failed discovery is not a profile. It must not poison future
                # lookups or fill the registry with every blocked URL.
                return
            if entry is None:
                entry = {
                    "key": key,
                    "version": INDEX_VERSION,
                    "host": scope["host"],
                    "path": scope["path"],
                    "query_keys": scope["query_keys"],
                    "scope": scope["scope"],
                    "scenario": spec.name,
                    "spec_fingerprint": spec_fingerprint(spec),
                    "first_seen_at": now_iso,
                    "success_count": 0,
                    "failure_streak": 0,
                    "route_stats": {},
                    "status": "active",
                    "schema_status": "unknown",
                    "schema_drift_streak": 0,
                    "schema_drift_count": 0,
                    "replay_enabled": False,
                    "replay_reenable_streak": 0,
                    "api_discoveries": [],
                    "api_replay_validated": None,
                }
                profiles[key] = entry

            observation_attempts = attempts or [{"backend": route, "usable": usable}]
            for attempt in observation_attempts:
                attempted_route = str(attempt.get("backend") or "")
                if attempted_route not in _ROUTE_NAMES:
                    continue
                stats = _route_stats(entry, attempted_route)
                stats["attempts"] += 1
                if bool(attempt.get("usable")):
                    stats["successes"] += 1
                else:
                    stats["failures"] += 1

            if usable:
                candidate = _candidate_descriptor(url, spec, result)
                if candidate is not None and candidate.get("replay_template") is not None:
                    entry["replay_template"] = candidate["replay_template"]
                _update_schema_state(entry, candidate or {}, route=route)
                if api_discovered:
                    entry["api_replay_validated"] = True if api_replay_validated else False
                if endpoint_contract:
                    discoveries = entry.setdefault("api_discoveries", [])
                    signature = json.dumps(
                        {
                            "url": endpoint_contract.get("url"),
                            "method": endpoint_contract.get("method"),
                        },
                        sort_keys=True,
                    )
                    seen = any(
                        json.dumps(
                            {"url": old.get("url"), "method": old.get("method")},
                            sort_keys=True,
                        )
                        == signature
                        for old in discoveries
                    )
                    if not seen:
                        discoveries.append(
                            {
                                "url": endpoint_contract.get("url"),
                                "method": endpoint_contract.get("method"),
                                "content_type": endpoint_contract.get("content_type"),
                                "matched_fields": endpoint_contract.get("matched_fields"),
                                "record_count": endpoint_contract.get("record_count"),
                                "score": endpoint_contract.get("score"),
                                "discovered_at": now_iso,
                                "validated": bool(api_replay_validated),
                            }
                        )
                        discoveries[:] = discoveries[-8:]
                entry.update(
                    {
                        "last_success_at": now_iso,
                        "last_success_epoch": now_epoch,
                        "last_elapsed_s": round(result.elapsed_s, 3),
                        "last_record_count": len(result.records),
                        "last_score": round(result.best_candidate.score, 2) if result.best_candidate else 0.0,
                        "preferred_route": route,
                        "candidate": candidate,
                        "success_count": _safe_int(entry.get("success_count")) + 1,
                        "failure_streak": 0,
                        "status": "active",
                        "last_error": None,
                    }
                )
            else:
                entry.update(
                    {
                        "last_failure_at": now_iso,
                        "last_failure_epoch": now_epoch,
                        "last_error": result.error,
                        "failure_streak": _safe_int(entry.get("failure_streak")) + 1,
                    }
                )
                if _safe_int(entry.get("failure_streak")) >= 2:
                    entry["status"] = "degraded"

            payload["version"] = INDEX_VERSION
            payload["updated_at"] = now_iso
            self._prune_unlocked(profiles)
            self._write_unlocked(payload)

    def invalidate(self, url: str, spec: ExtractionSpec, reason: str = "manual") -> bool:
        scope = url_scope(url)
        exact_key = profile_key(url, spec)
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            key, _ = self._find_entry_unlocked(
                payload["profiles"],
                exact_key,
                scope,
                spec_fingerprint(spec),
            )
            entry = payload["profiles"].get(key)
            if entry is None:
                return False
            entry.update({"status": "invalidated", "invalidated_at": _utc_now(), "last_error": reason[:300]})
            payload["updated_at"] = _utc_now()
            self._write_unlocked(payload)
            return True

    # -- Lot 3: domain profiles -------------------------------------------

    def observe_domain(
        self,
        url: str,
        *,
        route: str,
        success: bool,
        elapsed_s: float,
        requires_js: bool | None = None,
        challenge_seen: bool = False,
        endpoint_url: str | None = None,
    ) -> None:
        """Update the domain-level aggregate from one completed observation."""
        host = _normalized_host(url)
        if not host:
            return
        now_epoch = time.time()
        now_iso = _utc_now()
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            domains = payload["domains"]
            domain = domains.get(host)
            if domain is None:
                domain = _new_domain_profile(host)
                domains[host] = domain
            if success:
                domain["successes"] = _safe_int(domain.get("successes")) + 1
                domain["last_verified_at"] = now_iso
                domain["last_verified_epoch"] = now_epoch
                domain["routing"]["preferred"] = route
                latency_ms = max(0.0, _safe_float(elapsed_s) * 1000.0)
                samples = _safe_int(domain.get("latency_samples"))
                current_avg = _safe_float(domain.get("average_latency_ms"))
                domain["average_latency_ms"] = round((current_avg * samples + latency_ms) / (samples + 1), 1)
                domain["latency_samples"] = samples + 1
            else:
                domain["failures"] = _safe_int(domain.get("failures")) + 1
            if requires_js is not None:
                domain["behavior"]["requires_js"] = bool(requires_js) or bool(domain["behavior"].get("requires_js"))
            if challenge_seen:
                domain["behavior"]["challenge_seen"] = True
            domain["behavior"]["geo_sensitive"] = bool(domain["behavior"].get("geo_sensitive"))
            if endpoint_url:
                self._remember_domain_endpoint(domain, endpoint_url, now_iso)
            domain["routing"]["confidence"] = _fresh_confidence(
                base=0.3,
                successes=_safe_int(domain.get("successes")),
                failures=_safe_int(domain.get("failures")),
                last_verified_epoch=_safe_float(domain.get("last_verified_epoch"), now_epoch),
                now_epoch=now_epoch,
            )
            payload["version"] = INDEX_VERSION
            payload["updated_at"] = now_iso
            self._write_unlocked(payload)

    @staticmethod
    def _remember_domain_endpoint(domain: dict[str, Any], endpoint_url: str, now_iso: str) -> None:
        scope = url_scope(endpoint_url)
        endpoints = domain.setdefault("endpoints", [])
        signature = f"{scope['host']}{scope['path']}|{'|'.join(scope['query_keys'])}"
        for old in endpoints:
            old_signature = (
                f"{old.get('host')}{old.get('path')}|{'|'.join(old.get('query_keys') or [])}"
            )
            if old_signature == signature:
                old["last_seen_at"] = now_iso
                old["sightings"] = _safe_int(old.get("sightings")) + 1
                return
        endpoints.append(
            {
                "host": scope["host"],
                "path": scope["path"],
                "query_keys": scope["query_keys"],
                "first_seen_at": now_iso,
                "last_seen_at": now_iso,
                "sightings": 1,
            }
        )
        endpoints[:] = endpoints[-12:]

    # -- Lot 3: capability registry ----------------------------------------

    def register_capability(
        self,
        host: str,
        name: str,
        *,
        inputs: Mapping[str, Any],
        outputs: Mapping[str, Any],
        implementation: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Create (or return existing) capability. Deterministic, zero LLM."""
        host = _normalized_host("https://" + host) if "/" not in host else _normalized_host(host)
        now_iso = _utc_now()
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            caps = payload["capabilities"]
            capabilities = caps.setdefault(host, {})
            entry = capabilities.get(name)
            if entry is not None:
                return dict(entry)
            entry = _new_capability(host, name, inputs=inputs, outputs=outputs, implementation=implementation)
            capabilities[name] = entry
            payload["version"] = INDEX_VERSION
            payload["updated_at"] = now_iso
            self._write_unlocked(payload)
            # Attach the capability name to the domain profile.
            domains = payload["domains"]
            domain = domains.get(host)
            if domain is not None:
                known = set(domain.get("capabilities") or [])
                if name not in known:
                    known.add(name)
                    domain["capabilities"] = sorted(known)
        return dict(entry)

    def lookup_capability(self, host: str, name: str) -> dict[str, Any] | None:
        """Return the capability with live confidence, or None."""
        host = host.lower()
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            entry = payload["capabilities"].get(host, {}).get(name)
            if entry is None:
                return None
            entry = dict(entry)
        entry["confidence"] = _fresh_confidence(
            base=0.5,
            successes=_safe_int(entry.get("successes")),
            failures=_safe_int(entry.get("failures")),
            last_verified_epoch=_safe_float(entry.get("last_verified_epoch"), 0.0),
            now_epoch=time.time(),
        )
        return entry

    def observe_capability(
        self,
        host: str,
        name: str,
        *,
        success: bool,
        latency_ms: float,
        score: float | None = None,
        record_count: int | None = None,
    ) -> dict[str, Any] | None:
        """Update capability statistics and confidence from one execution."""
        host = host.lower()
        now_epoch = time.time()
        now_iso = _utc_now()
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            caps = payload["capabilities"]
            domains = payload["domains"]
            entry = caps.get(host, {}).get(name)
            if entry is None:
                return None
            if success:
                entry["successes"] = _safe_int(entry.get("successes")) + 1
                entry["last_verified_at"] = now_iso
                entry["last_verified_epoch"] = now_epoch
                entry["status"] = "active"
                samples = _safe_int(entry.get("latency_samples"))
                current_avg = _safe_float(entry.get("average_latency_ms"))
                entry["average_latency_ms"] = round((current_avg * samples + max(0.0, latency_ms)) / (samples + 1), 1)
                entry["latency_samples"] = samples + 1
                entry["last_latency_ms"] = round(max(0.0, latency_ms), 1)
                if score is not None:
                    entry["last_score"] = round(float(score), 3)
                if record_count is not None:
                    entry["last_record_count"] = _safe_int(record_count)
            else:
                entry["failures"] = _safe_int(entry.get("failures")) + 1
                if _safe_int(entry.get("failures")) >= 2:
                    entry["status"] = "degraded"
            entry["confidence"] = _fresh_confidence(
                base=0.5,
                successes=_safe_int(entry.get("successes")),
                failures=_safe_int(entry.get("failures")),
                last_verified_epoch=_safe_float(entry.get("last_verified_epoch"), now_epoch),
                now_epoch=now_epoch,
            )
            domain = domains.get(host)
            if domain is not None and success:
                domain["last_verified_at"] = now_iso
                domain["last_verified_epoch"] = now_epoch
            payload["version"] = INDEX_VERSION
            payload["updated_at"] = now_iso
            self._write_unlocked(payload)
            return dict(entry)

    def bump_capability_version(
        self,
        host: str,
        name: str,
        *,
        implementation: Mapping[str, Any],
        notes: str = "repaired",
    ) -> dict[str, Any] | None:
        """Redicovery repaired a capability: promote to the next version."""
        host = host.lower()
        now_iso = _utc_now()
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            entry = payload["capabilities"].get(host, {}).get(name)
            if entry is None:
                return None
            version = _safe_int(entry.get("version")) + 1
            entry["version"] = version
            entry["implementation"] = dict(implementation)
            entry["failures"] = 0
            entry["status"] = "active"
            entry["last_verified_at"] = now_iso
            entry["last_verified_epoch"] = time.time()
            versions = entry.setdefault("versions", [])
            versions.append({"version": version, "created_at": now_iso, "notes": notes[:200]})
            versions[:] = versions[-_MAX_CAPABILITY_VERSIONS:]
            payload["version"] = INDEX_VERSION
            payload["updated_at"] = now_iso
            self._write_unlocked(payload)
            return dict(entry)

    def list_capabilities(self, host: str | None = None) -> list[dict[str, Any]]:
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            result: list[dict[str, Any]] = []
            for domain_host, domain_caps in payload["capabilities"].items():
                if host is not None and domain_host != host.lower():
                    continue
                for entry in domain_caps.values():
                    result.append(dict(entry))
            return sorted(result, key=lambda e: (e.get("host", ""), e.get("name", "")))

    def domain_profile(self, host: str) -> dict[str, Any] | None:
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            return dict(payload["domains"][host.lower()]) if host.lower() in payload["domains"] else None

    def list_domains(self) -> list[dict[str, Any]]:
        with self._thread_lock, self._file_lock():
            payload = self._load_unlocked()
            return [dict(d) for d in payload["domains"].values()]

    def list_profiles(self) -> list[dict[str, Any]]:
        with self._thread_lock, self._file_lock():
            profiles = self._load_unlocked()["profiles"]
            return [dict(profile) for profile in sorted(profiles.values(), key=lambda item: item.get("last_success_epoch", 0), reverse=True)]

    def stats(self) -> dict[str, Any]:
        with self._thread_lock, self._file_lock():
            profiles = self._load_unlocked()["profiles"]
            now = time.time()
            fresh = sum(
                max(0.0, now - _safe_float(item.get("last_success_epoch"), now)) <= self.ttl_seconds
                for item in profiles.values()
            )
            degraded = sum(item.get("status") == "degraded" for item in profiles.values())
            drifted = sum(item.get("schema_status") == "drifted" for item in profiles.values())
            replay_enabled = sum(
                bool(item.get("replay_enabled")) and isinstance(item.get("replay_template"), Mapping)
                for item in profiles.values()
            )
            return {
                "path": str(self.path),
                "version": INDEX_VERSION,
                "profile_count": len(profiles),
                "fresh_count": fresh,
                "degraded_count": degraded,
                "drifted_count": drifted,
                "replay_enabled_count": replay_enabled,
                "ttl_seconds": self.ttl_seconds,
                "load_error": self._load_error,
            }

    def clear(self) -> None:
        with self._thread_lock, self._file_lock():
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self._load_error = None

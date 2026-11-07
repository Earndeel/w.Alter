from __future__ import annotations

import asyncio
import os
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

try:
    from scrapling.fetchers import AsyncStealthySession, StealthyFetcher
except ImportError:  # pragma: no cover - exercised only without the optional runtime
    AsyncStealthySession = None  # type: ignore[assignment,misc]
    StealthyFetcher = None  # type: ignore[assignment,misc]


Scalar = str | int | float | bool | None


async def _resolve_json(response: Any) -> Any:
    """Return response payload whether the Response exposes json() as an async
    coroutine (Playwright) or as a sync method (Scrapling custom Response)."""
    method = getattr(response, "json", None)
    if method is None:
        raise TypeError("response has no json() method")
    try:
        result = method()
        if asyncio.iscoroutine(result):
            return await result
        return result
    except TypeError:
        # Some non-async, non-callable-shaped methods raise only when awaited;
        # the plain sync call above is the canonical path in that case.
        raise


def normalize_token(value: str) -> str:
    """Normalize a JSON key for fuzzy, case-insensitive matching."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def is_json_response_candidate(resource_type: str, content_type: str) -> bool:
    """Accept JSON from XHR/fetch and direct JSON API navigations."""
    return resource_type in {"xhr", "fetch", "document"} and "json" in content_type.lower()


def is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def iter_nodes(value: Any, path: tuple[str, ...] = ()):
    yield path, value
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield from iter_nodes(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value[:100]):
            yield from iter_nodes(child, path + (f"[{index}]",))


def key_match_quality(key: str, aliases: Sequence[str]) -> int:
    normalized = normalize_token(key)
    best = 0
    for alias in aliases:
        candidate = normalize_token(alias)
        if not candidate:
            continue
        if normalized == candidate:
            best = max(best, 3)
        elif len(candidate) >= 5 and normalized.endswith(candidate):
            best = max(best, 2)
        elif len(candidate) >= 8 and candidate in normalized:
            best = max(best, 1)
    return best


def find_scalar(value: Any, aliases: Sequence[str]) -> tuple[Scalar, str] | None:
    """Find the most likely scalar value for a field in an arbitrary JSON tree."""
    candidates: list[tuple[int, int, Scalar, str]] = []

    def visit(node: Any, path: tuple[str, ...], inherited_quality: float = 0.0) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                key_text = str(key)
                quality = key_match_quality(key_text, aliases)
                if is_scalar(child) and (quality or inherited_quality):
                    score = max(quality * 100, int(inherited_quality * 60))
                    candidates.append((score, -len(path), child, ".".join(path + (key_text,))))
                visit(child, path + (key_text,), max(inherited_quality * 0.65, float(quality)))
        elif isinstance(node, list):
            for index, child in enumerate(node[:100]):
                visit(child, path + (f"[{index}]",), inherited_quality)

    visit(value, ())
    if not candidates:
        return None
    _, _, scalar, path = max(candidates, key=lambda item: (item[0], item[1]))
    return scalar, path


@dataclass(frozen=True)
class ExtractionSpec:
    """Fields used to identify useful payloads and project generic records."""

    expected_fields: Mapping[str, tuple[str, ...]]
    required_fields: tuple[str, ...] = ()
    min_records: int = 1
    score_threshold: float = 25.0
    name: str = "generic"
    # Optional last-resort browser projection.  Network extraction stays
    # endpoint-agnostic; a named DOM profile is used only when the site renders
    # useful records visibly but does not expose them in JSON responses.
    dom_profile: str | None = None
    # Query keys whose values may be substituted into a learned GET endpoint.
    replay_query_keys: tuple[str, ...] = ()


@dataclass
class ResponseCandidate:
    url: str
    method: str
    status: int
    content_type: str
    response_bytes: int
    elapsed_ms: float
    payload: Any
    matched_fields: tuple[str, ...]
    record_count: int
    score: float
    request_body_sha256: str | None = None
    request_body_bytes: int = 0

    def summary(self) -> dict[str, Any]:
        parsed = urlparse(self.url)
        return {
            "path": parsed.path,
            "method": self.method,
            "status": self.status,
            "content_type": self.content_type[:100],
            "response_bytes": self.response_bytes,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "matched_fields": list(self.matched_fields),
            "record_count": self.record_count,
            "score": round(self.score, 2),
            "request_body_sha256": self.request_body_sha256,
            "request_body_bytes": self.request_body_bytes,
        }


def find_record_list(payload: Any, spec: ExtractionSpec) -> tuple[str, list[dict[str, Any]]] | None:
    candidates: list[tuple[float, str, list[dict[str, Any]]]] = []
    for path, node in iter_nodes(payload):
        if not isinstance(node, list):
            continue
        records = [item for item in node[:100] if isinstance(item, dict)]
        if not records:
            continue
        coverage = 0.0
        for record in records[:30]:
            hits = sum(find_scalar(record, aliases) is not None for aliases in spec.expected_fields.values())
            coverage += hits / max(1, len(spec.expected_fields))
        coverage /= max(1, min(len(records), 30))
        score = coverage * 100 + min(len(records), 50)
        candidates.append((score, ".".join(path), records))
    if not candidates:
        return None
    _, path, records = max(candidates, key=lambda item: item[0])
    return path, records


def score_payload(payload: Any, spec: ExtractionSpec) -> tuple[float, tuple[str, ...], int]:
    """Score a JSON payload without knowing the website or endpoint name."""
    matched: list[str] = []
    for canonical, aliases in spec.expected_fields.items():
        if find_scalar(payload, aliases) is not None:
            matched.append(canonical)
    record_list = find_record_list(payload, spec)
    record_count = len(record_list[1]) if record_list else 0
    # A single-object answer (spot price, status, one entity: {"bitcoin": {"eur": …}}) is one record, as
    # project_records already treats it, when it carries most of what was asked; a blob matching a stray key is not.
    if (not record_list and isinstance(payload, Mapping) and spec.expected_fields
            and 2 * len(matched) >= len(spec.expected_fields)
            and all(field in matched for field in spec.required_fields)):
        record_count = 1
    score = len(matched) * 10 + min(record_count, 50)
    score += sum(15 for field in spec.required_fields if field in matched)
    if record_count >= spec.min_records:
        score += 10
    return score, tuple(sorted(matched)), record_count


def meets_spec(matched_fields: Sequence[str], record_count: int, spec: ExtractionSpec) -> bool:
    """Return whether a candidate is semantically usable, not merely large."""
    return record_count >= spec.min_records and all(
        field in matched_fields for field in spec.required_fields
    )


def project_records(payload: Any, spec: ExtractionSpec, limit: int = 100) -> list[dict[str, Any]]:
    """Project arbitrary repeated JSON objects into a small normalized shape."""
    record_list = find_record_list(payload, spec)
    if record_list is None:
        records = [payload] if isinstance(payload, dict) else []
        source_path = ""
    else:
        source_path, records = record_list

    projected: list[dict[str, Any]] = []
    for record in records[:limit]:
        item: dict[str, Any] = {"_source_path": source_path}
        for canonical, aliases in spec.expected_fields.items():
            found = find_scalar(record, aliases)
            if found is not None:
                value, path = found
                item[canonical] = value
                item[f"_{canonical}_path"] = path
        # Some APIs return one result object plus its price/currency in a
        # sibling context object.  Attach that context only when this payload
        # contains exactly one record; never guess across multiple records.
        if len(records) == 1:
            for canonical, aliases in spec.expected_fields.items():
                if canonical in item:
                    continue
                found = find_scalar(payload, aliases)
                if found is not None:
                    value, path = found
                    item[canonical] = value
                    item[f"_{canonical}_path"] = f"$context.{path}"
        if len(item) > 1:
            projected.append(item)
    return projected


def aggregate_records(candidates: Sequence[ResponseCandidate], spec: ExtractionSpec) -> list[dict[str, Any]]:
    """Merge valid responses from one page while removing duplicate retries."""
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not meets_spec(candidate.matched_fields, candidate.record_count, spec):
            continue
        for record in project_records(candidate.payload, spec):
            key = json.dumps(
                {name: value for name, value in record.items() if not name.startswith("_")},
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
    return records


@dataclass
class ExtractionResult:
    url: str
    elapsed_s: float
    candidates: list[ResponseCandidate] = field(default_factory=list)
    best_candidate: ResponseCandidate | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    html_bytes: int = 0
    error: str | None = None
    valid_candidate_count: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "elapsed_s": round(self.elapsed_s, 2),
            "error": self.error,
            "html_bytes": self.html_bytes,
            "candidate_count": len(self.candidates),
            "valid_candidate_count": self.valid_candidate_count,
            "json_candidates": [candidate.summary() for candidate in self.candidates],
            "best_candidate": self.best_candidate.summary() if self.best_candidate else None,
            "record_count": len(self.records),
            "records": self.records,
        }


def result_shape_fingerprint(result: ExtractionResult) -> str:
    """Fingerprint the normalized shape, not the response values."""
    candidate = result.best_candidate
    first_record = result.records[0] if result.records else {}
    shape = {
        "matched_fields": sorted(candidate.matched_fields) if candidate else [],
        "source_path": first_record.get("_source_path", ""),
        "field_paths": sorted(
            (key, value)
            for key, value in first_record.items()
            if key.startswith("_")
            and key.endswith("_path")
            and key != "_source_path"
            and isinstance(value, str)
        ),
    }
    encoded = json.dumps(shape, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def finalize_extraction_result(
    url: str,
    spec: ExtractionSpec,
    started: float,
    candidates: list[ResponseCandidate],
    *,
    html_bytes: int = 0,
    error: str | None = None,
) -> ExtractionResult:
    """Build the shared result contract for every browser backend.

    Scrapling and Camoufox capture responses through different APIs, but the
    ranking, validation, and record aggregation must stay identical. Keeping
    that policy here prevents a stealth fallback from becoming a second,
    subtly different extractor.
    """
    candidates.sort(
        key=lambda item: (
            meets_spec(item.matched_fields, item.record_count, spec),
            sum(field in item.matched_fields for field in spec.required_fields),
            item.score,
            item.record_count,
            item.response_bytes,
        ),
        reverse=True,
    )
    valid_candidate_count = sum(
        meets_spec(candidate.matched_fields, candidate.record_count, spec)
        for candidate in candidates
    )
    return ExtractionResult(
        url=url,
        elapsed_s=time.perf_counter() - started,
        candidates=candidates,
        best_candidate=candidates[0] if candidates else None,
        records=aggregate_records(candidates, spec),
        html_bytes=html_bytes,
        error=error,
        valid_candidate_count=valid_candidate_count,
    )


class PersistentSessionPool:
    """Keep one browser fingerprint/session alive per target domain."""

    def __init__(
        self,
        *,
        max_pages: int = 3,
        headless: bool = True,
        session_factory: Any = None,
    ) -> None:
        if session_factory is None and AsyncStealthySession is None:
            raise RuntimeError("scrapling AsyncStealthySession is required")
        self.max_pages = max(1, max_pages)
        self.headless = headless
        self._session_factory = session_factory or AsyncStealthySession
        self._sessions: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    @staticmethod
    def domain_key(url: str) -> str:
        parsed = urlparse(url)
        return parsed.netloc.lower() or parsed.path.split("/", 1)[0].lower()

    async def _get_session(self, url: str) -> Any:
        if self._closed:
            raise RuntimeError("persistent session pool is closed")
        domain = self.domain_key(url)
        async with self._lock:
            session = self._sessions.get(domain)
            if session is None:
                extra = {"proxy": os.environ["WALTER_BROWSE_PROXY"]} if os.environ.get("WALTER_BROWSE_PROXY") else {}
                session = self._session_factory(headless=self.headless, max_pages=self.max_pages, **extra)
                await session.start()
                self._sessions[domain] = session
            return session

    async def fetch(self, url: str, **kwargs: Any) -> Any:
        session = await self._get_session(url)
        return await session.fetch(url, **kwargs)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        sessions = list(self._sessions.values())
        self._sessions.clear()
        await asyncio.gather(*(session.close() for session in sessions), return_exceptions=True)


class UniversalExtractor:
    """Generic JSON-first extractor with bounded concurrent stealth sessions."""

    def __init__(
        self,
        *,
        concurrency: int = 3,
        timeout_ms: int = 90_000,
        candidate_wait_ms: int = 30_000,
        return_wait_ms: int = 250,
        headless: bool = True,
        persistent_sessions: bool = False,
        session_max_pages: int = 3,
        session_pool: PersistentSessionPool | None = None,
    ) -> None:
        if StealthyFetcher is None:
            raise RuntimeError("scrapling is required for the live extractor")
        self.concurrency = max(1, concurrency)
        self.timeout_ms = timeout_ms
        self.candidate_wait_ms = candidate_wait_ms
        self.return_wait_ms = return_wait_ms
        self.headless = headless
        self._session_pool = session_pool or (
            PersistentSessionPool(max_pages=session_max_pages, headless=headless)
            if persistent_sessions
            else None
        )

    async def extract_one(self, url: str, spec: ExtractionSpec) -> ExtractionResult:
        started = time.perf_counter()
        candidates: list[ResponseCandidate] = []
        response_tasks: list[asyncio.Task] = []
        candidate_ready = asyncio.Event()

        async def capture(response: Any) -> None:
            request = response.request
            content_type = response.headers.get("content-type", "")
            if not is_json_response_candidate(request.resource_type, content_type):
                return
            try:
                payload = await response.json()
            except Exception:
                return

            score, matched_fields, record_count = score_payload(payload, spec)
            request_body = getattr(request, "post_data", None)
            if not isinstance(request_body, str):
                request_body = None
            body_bytes = len(request_body.encode()) if request_body else 0
            candidate = ResponseCandidate(
                url=response.url,
                method=request.method,
                status=response.status,
                content_type=content_type,
                response_bytes=len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()),
                elapsed_ms=(time.perf_counter() - started) * 1000,
                payload=payload,
                matched_fields=matched_fields,
                record_count=record_count,
                score=score,
                request_body_sha256=(hashlib.sha256(request_body.encode()).hexdigest() if request_body else None),
                request_body_bytes=body_bytes,
            )
            candidates.append(candidate)
            if score >= spec.score_threshold and meets_spec(matched_fields, record_count, spec):
                candidate_ready.set()

        async def page_setup(page: Any) -> None:
            def on_response(response: Any) -> None:
                response_tasks.append(asyncio.create_task(capture(response)))

            page.on("response", on_response)

        async def page_action(_page: Any) -> None:
            try:
                await asyncio.wait_for(candidate_ready.wait(), self.candidate_wait_ms / 1000)
            except asyncio.TimeoutError:
                pass

        error: str | None = None
        html_bytes = 0
        try:
            fetch_kwargs = {
                "headless": self.headless,
                "network_idle": False,
                "load_dom": False,
                "wait": self.return_wait_ms,
                "timeout": self.timeout_ms,
                "page_setup": page_setup,
                "page_action": page_action,
                "locale": "en-US",
            }
            if os.environ.get("WALTER_BROWSE_PROXY") and self._session_pool is None:   # 2026-10-28: never the
                fetch_kwargs["proxy"] = os.environ["WALTER_BROWSE_PROXY"]                 # server's bare IP
            if self._session_pool is not None:
                response = await self._session_pool.fetch(url, **fetch_kwargs)
            else:
                response = await StealthyFetcher.async_fetch(url, **fetch_kwargs)
            if response_tasks:
                await asyncio.gather(*response_tasks, return_exceptions=True)
            html_bytes = len(getattr(response, "html_content", "") or "")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:500]

        return finalize_extraction_result(
            url,
            spec,
            started,
            candidates,
            html_bytes=html_bytes,
            error=error,
        )

    async def replay_one(
        self,
        source_url: str,
        spec: ExtractionSpec,
        replay_template: Mapping[str, Any],
        *,
        expected_shape_fingerprint: str | None = None,
        cookies: list[Mapping[str, Any]] | None = None,
    ) -> ExtractionResult:
        """Replay a learned GET JSON endpoint without navigating the source page.

        ``cookies`` (optional, domain-scoped by the caller) lets an API replay
        reuse the session's authentication context — only the cookies the
        endpoint needs, never the whole cookie jar.
        """
        from profile_index import render_replay_url

        started = time.perf_counter()
        try:
            target_url = render_replay_url(replay_template, source_url)
            fetch_kwargs = {
                "headless": self.headless,
                "network_idle": False,
                "load_dom": False,
                "wait": 0,
                "timeout": self.timeout_ms,
                "locale": "en-US",
            }
            if os.environ.get("WALTER_BROWSE_PROXY") and self._session_pool is None:   # 2026-10-28: never the
                fetch_kwargs["proxy"] = os.environ["WALTER_BROWSE_PROXY"]                 # server's bare IP
            if cookies:
                header = "; ".join(
                    f"{str(c.get('name', ''))}={str(c.get('value', ''))}" for c in cookies
                )
                fetch_kwargs["headers"] = {"Cookie": header}
            if self._session_pool is not None:
                response = await self._session_pool.fetch(target_url, **fetch_kwargs)
            else:
                response = await StealthyFetcher.async_fetch(target_url, **fetch_kwargs)
            # Scrapling's custom Response exposes a synchronous json()/text()
            # (requests-like); Playwright's Response (used in extract_one) is
            # async. resolve_json() normalizes both.
            payload = await _resolve_json(response)
            status = int(getattr(response, "status", 0) or 0)
            headers = getattr(response, "headers", {}) or {}
            content_type = str(headers.get("content-type", "application/json"))
            score, matched_fields, record_count = score_payload(payload, spec)
            candidate = ResponseCandidate(
                url=str(getattr(response, "url", "") or target_url),
                method="GET",
                status=status,
                content_type=content_type,
                response_bytes=len(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode()
                ),
                elapsed_ms=(time.perf_counter() - started) * 1000,
                payload=payload,
                matched_fields=matched_fields,
                record_count=record_count,
                score=score,
            )
            result = finalize_extraction_result(
                source_url,
                spec,
                started,
                [candidate],
                error=None
                if 200 <= status < 300 and "json" in content_type.lower()
                else (
                    f"Replay HTTP status {status}"
                    if not 200 <= status < 300
                    else "Replay content type is not JSON"
                ),
            )
            if result.error is not None:
                result.records = []
                result.valid_candidate_count = 0
            elif expected_shape_fingerprint:
                if result_shape_fingerprint(result) != expected_shape_fingerprint:
                    result.error = "Replay schema drift detected"
                    result.records = []
                    result.valid_candidate_count = 0
            return result
        except Exception as exc:
            return finalize_extraction_result(
                source_url,
                spec,
                started,
                [],
                error=f"{type(exc).__name__}: {exc}"[:500],
            )

    async def extract_many(self, requests: Sequence[tuple[str, ExtractionSpec]]) -> list[ExtractionResult]:
        semaphore = asyncio.Semaphore(self.concurrency)

        async def bounded(url: str, spec: ExtractionSpec) -> ExtractionResult:
            async with semaphore:
                return await self.extract_one(url, spec)

        return await asyncio.gather(*(bounded(url, spec) for url, spec in requests))

    async def close(self) -> None:
        if self._session_pool is not None:
            await self._session_pool.close()


def trip_spec() -> ExtractionSpec:
    return ExtractionSpec(
        name="flight",
        expected_fields={
            "price": ("accurateTotalPrice", "totalPrice", "farePrice", "averagePrice", "price"),
            "duration": ("duration", "transferDuration"),
            "flight_no": ("carrierFlightNo", "flightNo"),
            "airline": ("airlineInfo", "carrierAirlineInfo", "airline"),
            "airport_code": ("airportCode",),
            "currency": ("currency",),
        },
        required_fields=("price", "duration", "flight_no"),
        # Trip.com emits one journey per FlightMiddleSearch response; the
        # extractor aggregates several valid responses from the same page.
        min_records=1,
        score_threshold=35,
        replay_query_keys=("dcity", "acity", "ddate", "rdate", "triptype", "class", "sort", "locale", "curr"),
    )

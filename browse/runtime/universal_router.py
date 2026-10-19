from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from universal_extractor import (
    ExtractionResult,
    ExtractionSpec,
    ResponseCandidate,
    UniversalExtractor,
    finalize_extraction_result,
    meets_spec,
    normalize_token,
    score_payload,
)
from profile_index import ProfileIndex, _PROMOTE_MIN_SUCCESSES, profile_key
from webtop_client import DEFAULT_WEBTOP_CDP_URL, WebtopCdpClient

try:
    from browse_session import BrowseSession, SessionError  # noqa: F401
except ImportError:  # pragma: no cover - older deployments without Lot 2
    BrowseSession = None  # type: ignore[assignment,misc]
    SessionError = RuntimeError  # type: ignore[assignment,misc]


DEFAULT_CAMOUFOX_URL = "http://127.0.0.1:9377"
DEFAULT_USER_ID = "universal-extractor"
_CAPTURE_WAIT_SECONDS = 8.0
_MAX_CAPTURE_ITEMS = 80
_MAX_CAPTURE_CHARS = 1_200_000

# Signal-aware routing (Lot 1): cheap pre-flight probe and API replay downgrade.
_HTTP_PROBE_TIMEOUT = 7.0
_HTTP_PROBE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
# The probe must read far enough to see page BODY content, not just the <head>:
# judging a static page on its 2KB header is how books.toscrape got branded SPA.
_PROBE_BODY_BYTES = 262_144
_PROBE_JSON_LOOKAHEAD = 4096
_PROBE_SNIPPET_CHARS = 2048


# Older Camoufox Max workers expose Playwright navigation/evaluation over HTTP
# but do not expose a response event stream. This init script keeps the same
# JSON-first observation point as Scrapling for those workers. The current Max
# server uses native bounded response capture first.
_CAPTURE_INIT_SCRIPT = r"""
(() => {
  const state = { items: [], errors: [], startedAt: Date.now() };
  const maxItems = 80;
  const maxBodyChars = 1200000;

  const add = (entry) => {
    if (state.items.length >= maxItems || !entry || !entry.url) return;
    const body = typeof entry.body === "string" ? entry.body.slice(0, maxBodyChars) : "";
    const contentType = String(entry.contentType || "").toLowerCase();
    if (!body || (!contentType.includes("json") && !/^\s*[\[{]/.test(body))) return;
    let payload;
    try {
      payload = JSON.parse(body);
    } catch (_) {
      return;
    }
    state.items.push({
      url: String(entry.url),
      method: String(entry.method || "GET"),
      status: Number(entry.status || 0),
      contentType: entry.contentType || "application/json",
      responseBytes: body.length,
      requestBodyBytes: typeof entry.requestBody === "string" ? entry.requestBody.length : 0,
      payload,
    });
  };

  const nativeFetch = window.fetch;
  if (nativeFetch) {
    window.fetch = async function(...args) {
      const response = await nativeFetch.apply(this, args);
      try {
        const request = args[0] instanceof Request ? args[0] : null;
        const init = args[1] || {};
        const body = await response.clone().text();
        add({
          url: response.url || (typeof args[0] === "string" ? args[0] : request?.url),
          method: init.method || request?.method || "GET",
          status: response.status,
          contentType: response.headers.get("content-type") || "",
          requestBody: typeof init.body === "string" ? init.body : "",
          body,
        });
      } catch (error) {
        if (state.errors.length < 10) state.errors.push(String(error));
      }
      return response;
    };
  }

  const nativeOpen = XMLHttpRequest.prototype.open;
  const nativeSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.__universalRequest = { method, url: String(url) };
    return nativeOpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function(body) {
    this.addEventListener("load", () => {
      try {
        add({
          url: this.responseURL || this.__universalRequest?.url,
          method: this.__universalRequest?.method || "GET",
          status: this.status,
          contentType: this.getResponseHeader("content-type") || "",
          requestBody: typeof body === "string" ? body : "",
          body: this.responseText,
        });
      } catch (error) {
        if (state.errors.length < 10) state.errors.push(String(error));
      }
    });
    return nativeSend.call(this, body);
  };

  window.__UNIVERSAL_CAPTURE__ = state;
})();
"""

_CAPTURE_EXPRESSION = """
(() => {
  const state = window.__UNIVERSAL_CAPTURE__;
  return state ? state.items : [];
})()
"""

_PAGE_EXPRESSION = r"""
(() => {
  const contentType = document.contentType || "";
  const text = document.body?.textContent || "";
  let payload = null;
  if (contentType.toLowerCase().includes("json") || /^\s*[\[{]/.test(text)) {
    try { payload = JSON.parse(text); } catch (_) {}
  }
  return {
    url: location.href,
    contentType,
    htmlBytes: (document.documentElement?.outerHTML || "").length,
    payload,
  };
})()
"""


class CamoufoxMaxError(RuntimeError):
    """Raised when Camoufox Max cannot complete a browser operation."""


class CamoufoxMaxClient:
    """Small async client for the active Camoufox Max HTTP contract."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_CAMOUFOX_URL,
        user_id: str = DEFAULT_USER_ID,
        capture_wait_seconds: float = _CAPTURE_WAIT_SECONDS,
        timeout_seconds: float = 45.0,
        request_fn: Callable[[str, str, Mapping[str, Any] | None], dict[str, Any]] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.capture_wait_seconds = max(0.5, capture_wait_seconds)
        self.timeout_seconds = max(1.0, timeout_seconds)
        self._request_fn = request_fn or self._request_sync

    def _request_sync(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise CamoufoxMaxError(f"HTTP {exc.code} {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise CamoufoxMaxError(f"Camoufox Max unavailable at {self.base_url}: {exc.reason}") from exc
        try:
            result = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            raise CamoufoxMaxError(f"Camoufox Max returned non-JSON for {path} (HTTP {status})") from exc
        if not isinstance(result, dict):
            raise CamoufoxMaxError(f"Camoufox Max returned an invalid object for {path}")
        return result

    async def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._request_fn, method, path, payload)

    async def _evaluate(self, tab_id: str, expression: str) -> Any:
        response = await self._request(
            "POST",
            "/tab/evaluate",
            {"userId": self.user_id, "tabId": tab_id, "expression": expression},
        )
        if "result" not in response:
            raise CamoufoxMaxError(f"Camoufox Max evaluation omitted result: {response}")
        return response["result"]

    @staticmethod
    def _candidate(
        item: Mapping[str, Any],
        spec: ExtractionSpec,
        started: float,
        default_url: str,
    ) -> ResponseCandidate | None:
        payload = item.get("payload")
        if payload is None:
            return None
        score, matched_fields, record_count = score_payload(payload, spec)
        try:
            response_bytes = int(item.get("responseBytes") or 0)
        except (TypeError, ValueError):
            response_bytes = 0
        if response_bytes <= 0:
            response_bytes = len(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode()
            )
        try:
            status = int(item.get("status") or 200)
        except (TypeError, ValueError):
            status = 200
        try:
            request_body_bytes = int(item.get("requestBodyBytes") or 0)
        except (TypeError, ValueError):
            request_body_bytes = 0
        return ResponseCandidate(
            url=str(item.get("url") or default_url),
            method=str(item.get("method") or "GET"),
            status=status,
            content_type=str(item.get("contentType") or "application/json"),
            response_bytes=response_bytes,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            payload=payload,
            matched_fields=matched_fields,
            record_count=record_count,
            score=score,
            request_body_bytes=request_body_bytes,
        )

    async def extract_one(self, url: str, spec: ExtractionSpec) -> ExtractionResult:
        started = time.perf_counter()
        candidates: list[ResponseCandidate] = []
        seen_payloads: set[str] = set()
        tab_id: str | None = None
        html_bytes = 0
        error: str | None = None
        native_capture_supported: bool | None = None

        def add_candidate(item: Mapping[str, Any]) -> None:
            candidate = self._candidate(item, spec, started, url)
            if candidate is None:
                return
            fingerprint = hashlib.sha256(
                json.dumps(candidate.payload, ensure_ascii=False, sort_keys=True, default=str).encode()
            ).hexdigest()
            dedupe_key = f"{candidate.url}|{candidate.method}|{fingerprint}"
            if dedupe_key not in seen_payloads:
                seen_payloads.add(dedupe_key)
                candidates.append(candidate)

        try:
            created = await self._request(
                "POST",
                "/tab/new",
                {"userId": self.user_id, "listItemId": "universal-extractor"},
            )
            tab_id = str(created.get("tabId") or "")
            if not tab_id:
                raise CamoufoxMaxError(f"Camoufox Max did not return a tabId: {created}")
            await self._request(
                "POST",
                "/tab/add-init-script",
                {"userId": self.user_id, "tabId": tab_id, "script": _CAPTURE_INIT_SCRIPT},
            )
            await self._request(
                "POST",
                "/tab/navigate",
                {"userId": self.user_id, "tabId": tab_id, "url": url},
            )

            deadline = time.monotonic() + self.capture_wait_seconds
            while True:
                if native_capture_supported is not False:
                    try:
                        capture_response = await self._request(
                            "POST",
                            "/tab/network-captures",
                            {"userId": self.user_id, "tabId": tab_id},
                        )
                        native_capture_supported = True
                        captured = capture_response.get("captures", [])
                    except CamoufoxMaxError:
                        # Older Max workers do not have the native endpoint;
                        # retain the injected collector as a compatibility path.
                        native_capture_supported = False
                        captured = await self._evaluate(tab_id, _CAPTURE_EXPRESSION)
                else:
                    captured = await self._evaluate(tab_id, _CAPTURE_EXPRESSION)
                if isinstance(captured, list):
                    for item in captured[:_MAX_CAPTURE_ITEMS]:
                        if isinstance(item, Mapping):
                            add_candidate(item)
                if any(
                    meets_spec(candidate.matched_fields, candidate.record_count, spec)
                    for candidate in candidates
                ):
                    break
                if time.monotonic() >= deadline:
                    break
                await asyncio.sleep(0.25)

            page_info = await self._evaluate(tab_id, _PAGE_EXPRESSION)
            if isinstance(page_info, Mapping):
                try:
                    html_bytes = int(page_info.get("htmlBytes") or 0)
                except (TypeError, ValueError):
                    html_bytes = 0
                direct_payload = page_info.get("payload")
                if direct_payload is not None:
                    add_candidate(
                        {
                            "url": page_info.get("url") or url,
                            "method": "GET",
                            "status": 200,
                            "contentType": page_info.get("contentType") or "application/json",
                            "payload": direct_payload,
                        }
                    )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:500]
        finally:
            if tab_id:
                try:
                    await self._request(
                        "POST",
                        "/tab/close",
                        {"userId": self.user_id, "tabId": tab_id},
                    )
                except Exception:
                    # Closing a crashed tab must not hide the extraction result.
                    pass

        return finalize_extraction_result(
            url,
            spec,
            started,
            candidates,
            html_bytes=html_bytes,
            error=error,
        )


# ---------------------------------------------------------------------------
# Lot 1 — signal-aware routing: cheap pre-flight probe, API discovery and a
# validated HTTP replay downgrade. No LLM is involved anywhere in this layer.
# ---------------------------------------------------------------------------

def _looks_like_challenge(status: int, content_type: str, snippet: str) -> bool:
    """Recognize Cloudflare/challenge blocks from cheap signals only."""
    if status in (403, 429, 503):
        return True
    low = snippet.lower()
    markers = (
        "cf-challenge",
        "cloudflare",
        "captcha",
        "attention required",
        "just a moment",
        "enable javascript and cookies",
        "__cf_chl",
    )
    return any(marker in low for marker in markers)


def _html_utility_ratio(raw: str) -> float:
    """Rough useful-text ratio: visible text bytes / total bytes (0..1)."""
    if not raw:
        return 0.0
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    visible = len(" ".join(text.split()))
    return round(visible / max(1, len(raw)), 4)


async def http_probe(
    url: str,
    *,
    timeout: float = _HTTP_PROBE_TIMEOUT,
    content_hints: Sequence[str] | None = None,
    session: Any = None,
) -> dict[str, Any]:
    """Cheap GET probe that returns technical signals for routing.

    Reads up to _PROBE_BODY_BYTES so the heuristic judges the page body, not
    just the <head>. The body is kept in ``body`` (limited) so callers can
    score/extract directly from the probe result and avoid a second fetch
    when the contract can already be satisfied (HTTP_DIRECT_SUCCESS).

    ``content_hints`` are raw alias tokens of the requested fields (title,
    price...). When they are present in the body, ``content_present`` is True
    and a SPA label must not trigger browser escalation: the content the caller
    asked for is already in the static HTML.
    """
    started = time.perf_counter()
    result: dict[str, Any] = {
        "status": None,
        "content_type": None,
        "bytes": 0,
        "is_json": False,
        "has_scripts": False,
        "html_ratio": 0.0,
        "looks_spa": False,
        "content_present": False,
        "challenge": False,
        "redirect_target": None,
        "error": None,
        "probe_ms": 0,
        "body": None,
    }
    hints = [t for t in (content_hints or []) if t]
    if hints:
        hints = sorted({normalize_token(t) for t in hints})

    def _probe() -> None:
        request = urllib.request.Request(url, headers=_HTTP_PROBE_HEADERS, method="GET")
        try:
            if session is not None:
                from session_http import session_opener
                opener = session_opener(session, url)
                response_context = opener.open(request, timeout=timeout)
            else:
                response_context = urllib.request.urlopen(request, timeout=timeout)
            with response_context as response:
                result["status"] = response.status
                result["content_type"] = str(response.headers.get("content-type") or "").lower()
                result["redirect_target"] = response.geturl()
                raw = response.read(_PROBE_BODY_BYTES)
        except urllib.error.HTTPError as exc:
            result["status"] = exc.code
            result["content_type"] = str(exc.headers.get("content-type") or "").lower()
            try:
                raw = exc.read(_PROBE_BODY_BYTES)
            except Exception:
                raw = b""
        except urllib.error.URLError as exc:
            result["error"] = f"{type(exc).__name__}: {exc.reason}"
            return

        result["bytes"] = len(raw)
        snippet = raw.decode("utf-8", errors="replace")
        result["body"] = snippet
        result["is_json"] = "json" in (result["content_type"] or "") or snippet.lstrip().startswith(("{", "["))
        result["has_scripts"] = bool(re.search(r"<script", snippet, flags=re.I))
        result["html_ratio"] = _html_utility_ratio(snippet)
        # Content presence: are the requested field tokens actually in the
        # static body? If yes, never treat the page as an empty SPA shell.
        if hints and not result["is_json"]:
            normalized = normalize_token(snippet)
            result["content_present"] = all(hint in normalized for hint in hints)
        # JS-rendered SPA heuristic: lots of scripts, almost no visible text,
        # and no direct content in the page body.
        result["looks_spa"] = (
            result["has_scripts"]
            and result["html_ratio"] < 0.20
            and not result["is_json"]
            and not result["content_present"]
        )
        result["challenge"] = _looks_like_challenge(result["status"], result["content_type"], snippet)

    try:
        await asyncio.to_thread(_probe)
    except Exception as exc:  # pragma: no cover - defensive
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["probe_ms"] = round((time.perf_counter() - started) * 1000)
    return result


def _endpoint_contract(candidate: ResponseCandidate, *, max_contract_chars: int = 400) -> dict[str, Any] | None:
    """Describe a discovered XHR/API endpoint without storing response data.

    Only structural context is kept: method, URL (sans query values for
    sensitive keys), content type, matched fields. Secrets stay out.
    """
    if candidate is None:
        return None
    try:
        parsed = urllib.parse.urlsplit(candidate.url)
    except Exception:
        return None
    contract = {
        "url": candidate.url[:max_contract_chars],
        "method": candidate.method or "GET",
        "content_type": (candidate.content_type or "")[:100],
        "status": candidate.status,
        "matched_fields": list(candidate.matched_fields or []),
        "record_count": candidate.record_count or 0,
        "score": round(float(candidate.score or 0.0), 2),
    }
    # Keep the query string only if it contains parametrized tokens that a
    # replay can re-render; never persist credential-like values.
    if "json" in (candidate.content_type or "").lower():
        contract["query"] = parsed.query[:200]
    return contract


@dataclass
class RoutedResult:
    result: ExtractionResult
    route: str
    attempts: list[dict[str, Any]]
    escalation: dict[str, Any] | None = None
    profile: dict[str, Any] | None = None
    trace: list[str] | None = None
    signals: dict[str, Any] | None = None
    probe: dict[str, Any] | None = None
    downgrade: dict[str, Any] | None = None

    def summary(self) -> dict[str, Any]:
        payload = self.result.summary()
        payload.update(
            {
                "route": self.route,
                "attempts": self.attempts,
                "escalation": self.escalation,
                "profile": self.profile,
                "trace": self.trace,
                "signals": self.signals,
                # Probe stays cheap to serialize: status + content-type + flags.
                "probe": (
                    {
                        "status": self.probe.get("status"),
                        "content_type": self.probe.get("content_type"),
                        "is_json": self.probe.get("is_json"),
                        "looks_spa": self.probe.get("looks_spa"),
                        "content_present": self.probe.get("content_present"),
                        "challenge": self.probe.get("challenge"),
                        "probe_ms": self.probe.get("probe_ms"),
                    }
                    if self.probe
                    else None
                ),
                "downgrade": self.downgrade,
            }
        )
        return payload


class UniversalRouter:
    """Route structured extraction from cheap JSON-first to full stealth."""

    def __init__(
        self,
        *,
        scrapling_extractor: UniversalExtractor | None = None,
        camoufox_client: CamoufoxMaxClient | None = None,
        webtop_client: WebtopCdpClient | None = None,
        fallback_to_camoufox: bool = True,
        fallback_to_webtop: bool = True,
        profile_index: ProfileIndex | None = None,
    ) -> None:
        self.scrapling = scrapling_extractor
        self.camoufox = camoufox_client
        self.webtop = webtop_client
        self.fallback_to_camoufox = fallback_to_camoufox
        self.fallback_to_webtop = fallback_to_webtop
        self.profile_index = profile_index

    @staticmethod
    def _usable(result: ExtractionResult) -> bool:
        return bool(result.valid_candidate_count and result.records)

    @staticmethod
    def _attempt(backend: str, result: ExtractionResult) -> dict[str, Any]:
        return {
            "backend": backend,
            "usable": UniversalRouter._usable(result),
            "elapsed_s": round(result.elapsed_s, 2),
            "candidate_count": len(result.candidates),
            "record_count": len(result.records),
            "error": result.error,
        }

    @staticmethod
    def _error_result(url: str, spec: ExtractionSpec, message: str) -> ExtractionResult:
        return finalize_extraction_result(url, spec, time.perf_counter(), [], error=message)

    async def _run_backend(
        self,
        backend: str,
        url: str,
        spec: ExtractionSpec,
        profile_hit: Any = None,
    ) -> ExtractionResult:
        if backend == "replay":
            if self.scrapling is None or profile_hit is None:
                return self._error_result(url, spec, "Replay backend is unavailable")
            replay_one = getattr(self.scrapling, "replay_one", None)
            template = profile_hit.entry.get("replay_template")
            if replay_one is None or not isinstance(template, Mapping):
                return self._error_result(url, spec, "Learned replay template is unavailable")
            return await replay_one(
                url,
                spec,
                template,
                expected_shape_fingerprint=profile_hit.entry.get("shape_fingerprint"),
            )
        if backend == "api-replay":
            # Entry-point downgrade: reuse the learned JSON template that was
            # validated by the ExtractionSpec scorer on a prior visit.
            if self.scrapling is None or profile_hit is None:
                return self._error_result(url, spec, "API replay backend is unavailable")
            replay_one = getattr(self.scrapling, "replay_one", None)
            template = profile_hit.entry.get("replay_template")
            if replay_one is None or not isinstance(template, Mapping):
                return self._error_result(url, spec, "Learned API replay template is unavailable")
            return await replay_one(
                url,
                spec,
                template,
                expected_shape_fingerprint=profile_hit.entry.get("shape_fingerprint"),
            )
        if backend == "scrapling":
            if self.scrapling is None:
                return self._error_result(url, spec, "Scrapling backend is unavailable")
            return await self.scrapling.extract_one(url, spec)
        if backend == "camoufox-max":
            if self.camoufox is None:
                return self._error_result(url, spec, "Camoufox Max backend is unavailable")
            return await self.camoufox.extract_one(url, spec)
        if backend == "webtop-cdp":
            if self.webtop is None:
                return self._error_result(url, spec, "Webtop CDP backend is unavailable")
            return await self.webtop.extract_one(url, spec)
        raise ValueError(f"unknown backend: {backend}")

    def _discover_api_endpoints(
        self,
        result: ExtractionResult,
        source_url: str,
        *,
        max_endpoints: int = 3,
    ) -> list[ResponseCandidate]:
        """Extract XHR/network JSON candidates whose URL differs from the page.

        This is the API discovery signal: what the page displayed came from
        these endpoints. DOM candidates are excluded by construction.
        """
        discovered: list[ResponseCandidate] = []
        for candidate in result.candidates:
            method = (candidate.method or "GET").upper()
            if method == "DOM":
                continue
            if not candidate.payload or "json" not in (candidate.content_type or "").lower():
                continue
            try:
                candidate_host = urllib.parse.urlsplit(candidate.url).netloc
                source_host = urllib.parse.urlsplit(source_url).netloc
            except Exception:
                continue
            if not candidate_host or candidate_host != source_host:
                continue
            if candidate.url.rstrip("/") == source_url.rstrip("/"):
                continue
            discovered.append(candidate)
            if len(discovered) >= max_endpoints:
                break
        discovered.sort(key=lambda c: (c.score or 0.0), reverse=True)
        return discovered

    async def _api_replay_attempt(
        self,
        url: str,
        spec: ExtractionSpec,
        endpoint: ResponseCandidate,
        *,
        profile_hit: Any = None,
        session: Any = None,
    ) -> tuple[ExtractionResult, str]:
        """Replay a discovered API endpoint over plain HTTP, validated by the
        same ExtractionSpec scorer. No LLM. Returns (result, trace) where the
        trace is API_REPLAY_VALIDATED or API_REPLAY_FAILED.

        When a session is attached, only the cookies scoped to the endpoint's
        domain are forwarded (never the whole cookie jar).
        """
        started = time.perf_counter()
        trace = "API_REPLAY_FAILED"
        if self.scrapling is None:
            return (
                self._error_result(url, spec, "API replay unavailable (no scrapling extractor)"),
                trace,
            )
        try:
            from profile_index import build_replay_template

            template = build_replay_template(
                url,
                endpoint.url,
                method=endpoint.method or "GET",
                content_type=endpoint.content_type,
                dynamic_query_keys=spec.replay_query_keys,
            )
            if template is None:
                return (
                    self._error_result(url, spec, f"Endpoint not replay-safe: {endpoint.url[:160]}"),
                    trace,
                )
        except Exception as exc:
            return (
                self._error_result(url, spec, f"Replay template build failed: {exc}"[:300]),
                trace,
            )

        expected_shape = None
        if profile_hit is not None:
            expected_shape = profile_hit.entry.get("shape_fingerprint")
        cookies = None
        if session is not None:
            try:
                from browse_session import cookies_for_domain, SessionManager

                session_dir = SessionManager().storage_state_path(session)
                if session_dir.exists():
                    import json as _json

                    storage = _json.loads(session_dir.read_text("utf-8"))
                    jar = storage.get("cookies", []) or []
                    cookies = cookies_for_domain(jar, urllib.parse.urlsplit(endpoint.url).netloc) or None
            except Exception:
                cookies = None  # session storage unavailable: replay unauthenticated
        replay_result = await self.scrapling.replay_one(
            url,
            spec,
            template,
            expected_shape_fingerprint=expected_shape,
            cookies=cookies,
        )
        if self._usable(replay_result):
            trace = "API_REPLAY_VALIDATED"
            replay_result.elapsed_s = round(time.perf_counter() - started, 3)
            return replay_result, trace
        if replay_result.error:
            replay_result.error = f"api-replay: {replay_result.error}"[:300]
        return replay_result, trace

    async def _run_api_downgrade(
        self,
        url: str,
        spec: ExtractionSpec,
        browser_result: ExtractionResult,
        *,
        profile_hit: Any = None,
        session: Any = None,
    ) -> tuple[ExtractionResult | None, str]:
        """Try HTTP replay downgrade; keep browser result as immediate fallback.

        Returns (None, trace) when no replayable endpoint exists or the replay
        failed — the caller keeps the browser result (reversible downgrade).
        """
        endpoints = self._discover_api_endpoints(browser_result, url)
        if not endpoints:
            return None, ""
        replay_result, trace = await self._api_replay_attempt(
            url, spec, endpoints[0], profile_hit=profile_hit, session=session
        )
        if trace == "API_REPLAY_VALIDATED":
            return replay_result, trace
        return None, trace

    def _auto_order(
        self,
        preferred_route: str | None,
        *,
        replay_available: bool = False,
        signals: Mapping[str, Any] | None = None,
    ) -> list[str]:
        """Build the normal chain, moving only a fresh validated hint to front.

        Signal-aware: after a cheap probe, a direct-JSON endpoint skips the
        browser ladder entirely and a challenge skips the plain HTTP attempt.
        """
        order = ["scrapling"]
        signals = signals or {}
        is_json = bool(signals.get("is_json"))
        challenge = bool(signals.get("challenge"))
        looks_spa = bool(signals.get("looks_spa"))

        if self.fallback_to_camoufox:
            # Keep an unavailable Camoufox attempt visible for diagnostics; the
            # existing router contract reports it before recommending Webtop.
            order.append("camoufox-max")
            if self.fallback_to_webtop and self.webtop is not None:
                order.append("webtop-cdp")

        if is_json:
            # Direct JSON endpoint: no browser needed at all (downgrade-first).
            order = ["scrapling"]
        elif challenge:
            # Challenge/anti-bot: skip bare HTTP, jump straight to stealth.
            order = ["camoufox-max"]
            if self.fallback_to_webtop and self.webtop is not None:
                order.append("webtop-cdp")
        elif looks_spa:
            # JS-rendered: keep HTTP first (cheap negative), then browser.
            order = ["scrapling", "camoufox-max"]
            if self.fallback_to_webtop and self.webtop is not None:
                order.append("webtop-cdp")

        if replay_available:
            order.insert(0, "replay")
        if preferred_route == "api-replay" and "api-replay" not in order:
            order.insert(0, "api-replay")
        if preferred_route in order:
            order.remove(preferred_route)
            order.insert(0, preferred_route)
        return order

    @staticmethod
    def _escalation(mode: str, last_backend: str, attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
        if mode == "scrapling":
            return None
        recommended = {
            "replay": "scrapling",
            "api-replay": "scrapling",
            "scrapling": "webtop-cdp",
            "camoufox-max": "webtop-cdp",
            "webtop-cdp": "brave-mac-cdp",
        }.get(last_backend, "brave-mac-cdp")
        return {
            "recommended_backend": recommended,
            "reason": "No semantically valid candidate survived the attempted extraction routes",
        }

    async def extract_one(
        self,
        url: str,
        spec: ExtractionSpec,
        *,
        mode: str = "auto",
        session: Any = None,
    ) -> RoutedResult:
        if mode not in {"auto", "scrapling", "camoufox", "webtop"}:
            raise ValueError("mode must be auto, scrapling, camoufox, or webtop")

        authenticated_session = session is not None and (session.identity != 'anonymous' or session.authenticated or session.cookie_count > 0)
        if authenticated_session and mode != 'auto':
            return RoutedResult(self._error_result(url, spec, 'authenticated browser adapter not qualified; use managed HTTP auto mode'), 'session-http', [])
        attempts: list[dict[str, Any]] = []
        last_result: ExtractionResult | None = None
        signals: dict[str, Any] | None = None
        probe: dict[str, Any] | None = None
        trace: list[str] = []
        downgrade: dict[str, Any] | None = None
        profile_hit = self.profile_index.lookup(url, spec) if self.profile_index is not None and not authenticated_session else None
        profile_summary = (
            profile_hit.summary()
            if profile_hit is not None
            else ({"hit": False, "key": profile_key(url, spec)} if self.profile_index is not None else None)
        )

        # Lot 1: cheap signal probe (auto mode only). Zero LLM.
        if mode == "auto":
            hints = sorted(
                {
                    token
                    for aliases in spec.expected_fields.values()
                    for token in (normalize_token(a) for a in aliases)
                    if token
                }
            )
            probe = await http_probe(url, content_hints=hints, **({"session": session} if authenticated_session else {}))
            signals = {
                "status": probe.get("status"),
                "content_type": probe.get("content_type"),
                "is_json": probe.get("is_json"),
                "has_scripts": probe.get("has_scripts"),
                "html_ratio": probe.get("html_ratio"),
                "looks_spa": probe.get("looks_spa"),
                "content_present": probe.get("content_present"),
                "challenge": probe.get("challenge"),
            }
            if probe.get("is_json"):
                trace.append("API_JSON_DIRECT")
            elif probe.get("challenge"):
                trace.append("CHALLENGE_DETECTED")
            elif probe.get("content_present"):
                trace.append("HTML_STATIC")
            elif probe.get("looks_spa"):
                trace.append("SPA_DETECTED")
            else:
                trace.append("HTTP_ATTEMPT")

            # HTTP_DIRECT_PATH: score/extract straight from the probe body and
            # only fetch again if the body is missing or the contract fails.
            body = probe.get("body") if probe.get("status") and 200 <= probe["status"] < 300 else None
            if probe.get("is_json") and body:
                try:
                    direct_payload = json.loads(body)
                    direct_score, direct_matched, direct_count = score_payload(direct_payload, spec)
                    if meets_spec(direct_matched, direct_count, spec):
                        direct_started = time.perf_counter()
                        candidate = ResponseCandidate(
                            url=url,
                            method="GET",
                            status=probe.get("status") or 200,
                            content_type=probe.get("content_type") or "application/json",
                            response_bytes=len(body.encode("utf-8", errors="replace")),
                            elapsed_ms=(time.perf_counter() - direct_started) * 1000,
                            payload=direct_payload,
                            matched_fields=direct_matched,
                            record_count=direct_count,
                            score=direct_score,
                        )
                        direct_result = finalize_extraction_result(
                            url, spec, direct_started, [candidate]
                        )
                        if self._usable(direct_result):
                            if self.profile_index is not None and not authenticated_session:
                                self.profile_index.observe(
                                    url,
                                    spec,
                                    route="scrapling",
                                    result=direct_result,
                                    attempts=[{"backend": "probe", "usable": True}],
                                    api_discovered=False,
                                    api_replay_validated=None,
                                )
                                # Lot 3: promote a capability after repeatable success.
                                self._learn_capability_on_success(url, spec, "probe-http", direct_result, direct_result.elapsed_s)
                                self.profile_index.observe_domain(
                                    url,
                                    route="probe-http",
                                    success=True,
                                    elapsed_s=direct_result.elapsed_s,
                                    endpoint_url=url,
                                )
                            trace.append("HTTP_DIRECT_SUCCESS")
                            return RoutedResult(
                                result=direct_result,
                                route="probe-http",
                                attempts=[{"backend": "probe", "usable": True}],
                                profile=dict(profile_summary) if profile_summary is not None else None,
                                trace=trace,
                                signals=signals,
                                probe=probe,
                            )
                except (ValueError, TypeError):
                    pass  # not parseable JSON: fall through to the normal ladder
            elif body and "html" in (probe.get("content_type") or ""):
                # Static HTML fast path: the contract may already be satisfied
                # in the body the probe fetched. Zero second request, zero browser.
                try:
                    # Reading mode (content_only): the spec asks for free text.
                    from universal_extractor import normalize_token as _norm

                    wants_content = any(
                        "content" in _norm(key) or "text" in _norm(key)
                        for key in spec.expected_fields
                    )
                    if wants_content:
                        try:
                            from bs4 import BeautifulSoup

                            soup = BeautifulSoup(body, "lxml")
                            for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
                                tag.decompose()
                            visible_text = soup.get_text(separator="\n", strip=True)
                            visible_text = re.sub(r"\n{2,}", "\n", visible_text).strip()
                            if len(visible_text) >= 120:
                                content_candidate = ResponseCandidate(
                                    url=url,
                                    method="DOM",
                                    status=200,
                                    content_type="text/html",
                                    response_bytes=len(body.encode("utf-8", errors="replace")),
                                    elapsed_ms=0,
                                    payload={"content": visible_text[:200_000]},
                                    matched_fields={"content"},
                                    record_count=1,
                                    score=100.0,
                                )
                                content_result = finalize_extraction_result(
                                    url, spec, time.perf_counter(), [content_candidate]
                                )
                                if self._usable(content_result) and content_result.records:
                                    if self.profile_index is not None and not authenticated_session:
                                        self.profile_index.observe(
                                            url,
                                            spec,
                                            route="static-html",
                                            result=content_result,
                                            attempts=[{"backend": "probe", "usable": True}],
                                        )
                                    trace.append("HTML_CONTENT_DIRECT")
                                    return RoutedResult(
                                        result=content_result,
                                        route="static-html",
                                        attempts=[{"backend": "probe", "usable": True}],
                                        profile=(
                                            dict(profile_summary) if profile_summary is not None else None
                                        ),
                                        trace=trace,
                                        signals=signals,
                                        probe=probe,
                                    )
                        except ImportError:
                            pass  # bs4 unavailable: normal ladder
                    from static_html import extract_static_html

                    static_result = extract_static_html(url, body, spec)
                    if self._usable(static_result):
                        if self.profile_index is not None and not authenticated_session:
                            self.profile_index.observe(
                                url,
                                spec,
                                route="static-html",
                                result=static_result,
                                attempts=[{"backend": "probe", "usable": True}],
                                api_discovered=False,
                                api_replay_validated=None,
                            )
                            # Lot 3: promote a capability after repeatable success.
                            self._learn_capability_on_success(url, spec, "static-html", static_result, static_result.elapsed_s)
                            self.profile_index.observe_domain(
                                url,
                                route="static-html",
                                success=True,
                                elapsed_s=static_result.elapsed_s,
                                endpoint_url=url,
                            )
                        trace.append("HTML_STATIC_DIRECT")
                        return RoutedResult(
                            result=static_result,
                            route="static-html",
                            attempts=[{"backend": "probe", "usable": True}],
                            profile=(
                                dict(profile_summary) if profile_summary is not None else None
                            ),
                            trace=trace,
                            signals=signals,
                            probe=probe,
                        )
                except ImportError:
                    pass  # static extractor unavailable: normal ladder

        if authenticated_session:
            return RoutedResult(self._error_result(url, spec, 'managed authenticated HTTP did not satisfy the contract; no anonymous fallback'),
                                'session-http', [{'backend':'session-http', 'usable':False}], trace=trace, signals=signals, probe=probe)

        if mode == "auto":
            order = self._auto_order(
                profile_hit.preferred_route if profile_hit is not None else None,
                replay_available=bool(profile_hit and profile_hit.replay_available),
                signals=signals,
            )
        else:
            order = {
                "scrapling": ["scrapling"],
                "camoufox": ["camoufox-max"],
                "webtop": ["webtop-cdp"],
            }[mode]

        for backend in order:
            result = await self._run_backend(backend, url, spec, profile_hit)
            attempt = self._attempt(backend, result)
            attempts.append(attempt)
            last_result = result
            if self._usable(result):
                # Lot 1: API discovery + validated HTTP replay downgrade.
                # Browser/context stays live (Camoufox Max server keeps the
                # browser warm); the browser result is the immediate fallback
                # if the replay fails (reversible downgrade).
                if backend in ("camoufox-max", "webtop-cdp"):
                    replay_result, replay_trace = await self._run_api_downgrade(
                        url,
                        spec,
                        result,
                        profile_hit=profile_hit,
                        session=session,
                    )
                    if replay_trace:
                        trace.append(replay_trace)
                    if replay_result is not None:
                        downgrade = {
                            "from": backend,
                            "to": "api-replay",
                            "validated": True,
                            "endpoint": (
                                _endpoint_contract(replay_result.best_candidate)
                                if replay_result.best_candidate is not None
                                else None
                            ),
                        }
                        trace.append("DOWNGRADE_HTTP")
                        result = replay_result
                        backend = "api-replay"
                        if self.profile_index is not None:
                            self.profile_index.observe(
                                url,
                                spec,
                                route=backend,
                                result=result,
                                attempts=attempts,
                                api_discovered=True,
                                api_replay_validated=True,
                                endpoint_contract=downgrade.get("endpoint"),
                            )
                        profile = dict(profile_summary) if profile_summary is not None else None
                        if profile is not None:
                            profile.update(
                                {
                                    "route_used": "api-replay",
                                    "route_learned": "api-replay",
                                    "downgraded_from": downgrade["from"],
                                }
                            )
                        return RoutedResult(
                            result=result,
                            route=backend,
                            attempts=attempts,
                            profile=profile,
                            trace=trace,
                            signals=signals,
                            probe=probe,
                            downgrade=downgrade,
                        )
                    trace.append("FALLBACK_BROWSER")
                if self.profile_index is not None:
                    self.profile_index.observe(
                        url,
                        spec,
                        route=backend,
                        result=result,
                        attempts=attempts,
                        api_discovered=False,
                        api_replay_validated=None,
                    )
                    # Lot 3: promote a capability once a journey is repeatable.
                    self._learn_capability_on_success(url, spec, backend, result, result.elapsed_s)
                    self.profile_index.observe_domain(
                        url,
                        route=backend,
                        success=True,
                        elapsed_s=result.elapsed_s,
                        endpoint_url=(result.best_candidate.url if result.best_candidate else None),
                    )
                profile = dict(profile_summary) if profile_summary is not None else None
                if profile is not None:
                    previous_route = profile.get("stored_route")
                    profile.update(
                        {
                            "route_used": backend,
                            "route_learned": backend,
                            "relearned": bool(
                                backend != "replay" and previous_route and previous_route != backend
                            ),
                            "replayed": backend == "replay",
                        }
                    )
                return RoutedResult(
                    result=result,
                    route=backend,
                    attempts=attempts,
                    profile=profile,
                    trace=trace,
                    signals=signals,
                    probe=probe,
                )
            if mode != "auto":
                break

        assert last_result is not None
        last_backend = attempts[-1]["backend"]
        if self.profile_index is not None:
            self.profile_index.observe(
                url,
                spec,
                route=last_backend,
                result=last_result,
                attempts=attempts,
            )
        profile = dict(profile_summary) if profile_summary is not None else None
        if profile is not None:
            profile["route_used"] = last_backend
            profile["route_learned"] = profile.get("stored_route")
        return RoutedResult(
            result=last_result,
            route=last_backend,
            attempts=attempts,
            escalation=self._escalation(mode, last_backend, attempts),
            profile=profile,
            trace=trace,
            signals=signals,
            probe=probe,
        )

    def _learn_capability_on_success(
        self,
        url: str,
        spec: ExtractionSpec,
        route: str,
        result: ExtractionResult,
        elapsed_s: float,
    ) -> None:
        """Auto-promote a capability after repeatable success (zero LLM).

        Only operations with an identifiable name (search/find/list/...)
        become capabilities; plain page fetches never do. Two consecutive
        successes on the same journey are required before promotion.
        """
        if self.profile_index is None:
            return
        try:
            from profile_index import cap_capability_name  # noqa: F401
        except ImportError:
            pass
        from profile_index import capability_name_from_spec, parameterize_url_slots, url_scope

        scope = url_scope(url)
        name = capability_name_from_spec(spec, scope)
        if not name:
            return
        hit = self.profile_index.lookup(url, spec)
        if hit is None or int(hit.entry.get("success_count") or 0) < _PROMOTE_MIN_SUCCESSES:
            return
        best = result.best_candidate
        recipe_url = parameterize_url_slots(url, dynamic_keys=spec.replay_query_keys)
        impl: dict[str, Any] = {
            "type": "api-replay" if route in ("api-replay", "replay") else ("static-html" if route == "static-html" else "browse"),
            "route": route,
            "url": recipe_url,
            "page_url": url,  # original page for rediscovery after a recipe break
            "expected_fields": {
                str(key): list(aliases) for key, aliases in spec.expected_fields.items()
            },
            "required_fields": list(spec.required_fields),
            "min_records": spec.min_records,
            "score_threshold": spec.score_threshold,
        }
        if best is not None and best.url != url:
            impl["endpoint"] = best.url
        try:
            capability = self.profile_index.register_capability(
                scope["host"],
                name,
                inputs={
                    key: "string" for key in scope["query_keys"]
                } or {"q": "string"},
                outputs={
                    str(key): "any" for key in spec.expected_fields
                },
                implementation=impl,
            )
            self.profile_index.observe_capability(
                scope["host"],
                name,
                success=True,
                latency_ms=max(0.0, float(elapsed_s) * 1000.0),
                score=result.best_candidate.score if result.best_candidate else None,
                record_count=len(result.records),
            )
        except Exception:
            pass  # learning is best-effort, never breaks extraction

    async def close(self) -> None:
        if self.scrapling is not None:
            await self.scrapling.close()
        if self.webtop is not None:
            await self.webtop.close()


def _parse_expected_fields(raw: str) -> dict[str, tuple[str, ...]]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"--expected-fields must be JSON: {exc}") from exc
    if not isinstance(value, dict) or not value:
        raise argparse.ArgumentTypeError("--expected-fields must be a non-empty JSON object")
    parsed: dict[str, tuple[str, ...]] = {}
    for canonical, aliases in value.items():
        if isinstance(aliases, str):
            aliases = [aliases]
        if not isinstance(aliases, list) or not aliases:
            raise argparse.ArgumentTypeError(f"Field {canonical!r} needs a non-empty alias list")
        parsed[str(canonical)] = tuple(str(alias) for alias in aliases)
    return parsed


def _spec_from_args(args: argparse.Namespace) -> ExtractionSpec:
    if args.profile:
        from panel_server import SCENARIOS, spec_for

        scenario = SCENARIOS.get(args.profile)
        if scenario is None:
            known = ", ".join(sorted(SCENARIOS))
            raise SystemExit(f"Unknown profile {args.profile!r}; choose one of: {known}")
        return spec_for(scenario)
    if not args.expected_fields:
        if getattr(args, "capability", None):
            # The capability implementation carries its own contract.
            return ExtractionSpec(
                name=getattr(args, "capability", "capability").split("/")[-1],
                expected_fields={"value": ("value",)},
                required_fields=("value",),
                min_records=1,
                score_threshold=1.0,
            )
        raise SystemExit("Provide --profile or --expected-fields JSON")
    return ExtractionSpec(
        name="cli",
        expected_fields=_parse_expected_fields(args.expected_fields),
        required_fields=tuple(args.required_field),
        min_records=args.min_records,
        score_threshold=args.score_threshold,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Universal JSON-first web extraction router")
    parser.add_argument("--url", required=False, help="Target URL (required unless --capability is used)")
    parser.add_argument("--profile", help="Built-in test-lab profile, e.g. flight-search")
    parser.add_argument("--expected-fields", help="JSON object mapping canonical fields to aliases")
    parser.add_argument("--required-field", action="append", default=[], help="Required canonical field (repeatable)")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--score-threshold", type=float, default=25.0)
    parser.add_argument("--mode", choices=("auto", "scrapling", "camoufox", "webtop"), default="auto")
    parser.add_argument("--camoufox-url", default=DEFAULT_CAMOUFOX_URL)
    parser.add_argument("--camoufox-user-id", default=DEFAULT_USER_ID)
    parser.add_argument("--capture-wait", type=float, default=_CAPTURE_WAIT_SECONDS)
    parser.add_argument("--webtop-cdp-url", default=DEFAULT_WEBTOP_CDP_URL)
    parser.add_argument("--webtop-wait", type=float, default=12.0)
    parser.add_argument("--webtop-navigation-timeout", type=float, default=35.0)
    parser.add_argument("--pretty", action="store_true")
    # Lot 2 — first-class sessions.
    parser.add_argument("--session-id", default=None, help="Reuse a persisted session by id")
    parser.add_argument("--identity", choices=("anonymous", "personal", "temporary"), default="anonymous")
    parser.add_argument("--persistent", action="store_true", help="Persist the session after the task")
    parser.add_argument("--network", choices=("local", "vpn", "proxy"), default="local",
                        help="Session network scope (local is ALWAYS the default)")
    parser.add_argument("--country", default=None, help="Exit country for vpn/proxy network scope")
    parser.add_argument("--session-save", action="store_true", help="Explicitly save after completion")
    # Lot 3 — capability fast path (web memory).
    parser.add_argument("--capability", default=None,
                        help="Execute a learned capability, e.g. dummyjson.com/product_search")
    parser.add_argument("--capability-inputs", default=None,
                        help='JSON object of capability inputs, e.g. {"category":"laptops"}')
    parser.add_argument("--no-cache", action="store_true", help="Force fresh execution (bypass result cache)")
    # Lot 4 correction — search-lite route (universal web entry point).
    parser.add_argument("--search", default=None,
                        help="Web search query (lite path: no browser, no LLM; results as links+snippets)")
    parser.add_argument("--search-count", type=int, default=5, help="Max search results (1-8)")
    return parser


async def _run_cli(args: argparse.Namespace) -> int:
    if not args.capability and not args.url and not args.search:
        raise SystemExit("Provide --url, --search, or --capability")
    if args.search:
        # Lot 4 correction — search-lite: the universal web entry point's
        # lightest route. No LLM, no browser, ~1s.
        from search_lite import search_lite

        payload = search_lite(args.search, count=max(1, min(args.search_count, 8)))
        print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None, default=str))
        return 0 if payload["success"] else 2
    spec = _spec_from_args(args)
    scrapling: UniversalExtractor | None = None
    try:
        scrapling = UniversalExtractor(
            concurrency=1,
            candidate_wait_ms=30_000,
            return_wait_ms=250,
            persistent_sessions=True,
            session_max_pages=2,
        )
    except Exception:
        # The route remains usable in explicit Camoufox mode when the optional
        # Scrapling virtualenv is not the interpreter running this command.
        scrapling = None

    # Lot 2 — Session Manager: acquire a first-class session when requested.
    from browse_session import SessionManager

    session: BrowseSession | None = None
    camoufox_user_id = args.camoufox_user_id
    session_trace: dict[str, Any] | None = None
    sctx = SessionManager()
    if args.session_id or args.identity != "anonymous" or args.network != "local" or args.persistent:
        if args.session_id:
            try:
                session = sctx.load(args.session_id)
            except SessionError:
                raise SessionError('requested managed session unavailable; anonymous fallback refused') from None
        if session is None:
            session = sctx.create(
                session_id=args.session_id,
                identity=args.identity,
                persistent=args.persistent,
                network=args.network,
                country=args.country,
            )
        session_trace = session.summary()
        camoufox_user_id = f"session-{session.id}"
        # Session-scoped network: only when explicitly requested (network=vpn|proxy).
        if session.network in ("vpn", "proxy") and session.country:
            client = CamoufoxMaxClient(base_url=args.camoufox_url, user_id=camoufox_user_id)
            proxy = {"server": "http://127.0.0.1:1080"}  # nordvpn-proxy FR container (session-scoped)
            await asyncio.to_thread(
                client._request_sync, "POST", "/session/new",
                {"userId": camoufox_user_id, "proxy": proxy},
            )
            sctx.log_event(session, "NETWORK_ROUTE", mode=session.network, country=session.country)

    router = UniversalRouter(
        scrapling_extractor=scrapling,
        camoufox_client=CamoufoxMaxClient(
            base_url=args.camoufox_url,
            user_id=camoufox_user_id,
            capture_wait_seconds=args.capture_wait,
        ),
        webtop_client=WebtopCdpClient(
            cdp_url=args.webtop_cdp_url,
            wait_seconds=args.webtop_wait,
            navigation_timeout_seconds=args.webtop_navigation_timeout,
        ),
        profile_index=ProfileIndex(),
    )
    try:
        if args.capability:
            # Lot 3 — capability fast path (virtual API execution).
            from capability_engine import CapabilityEngine

            host, _, name = args.capability.partition("/")
            host = host or args.capability
            name = name or "default"
            inputs = None
            if args.capability_inputs:
                inputs = json.loads(args.capability_inputs)
            engine = CapabilityEngine(router, index=ProfileIndex())
            cresult = await engine.execute(
                host,
                name,
                inputs,
                spec=spec,
                url=None,
                mode=args.mode,
                session=session,
                force_fresh=args.no_cache,
            )
            print(
                json.dumps(
                    cresult.to_dict(),
                    ensure_ascii=False,
                    indent=2 if args.pretty else None,
                    default=str,
                )
            )
            return 0 if cresult.records else 2
        routed = await router.extract_one(args.url, spec, mode=args.mode, session=session)
        if session is not None and session.persistent and args.session_save:
            sctx.save(session)
    finally:
        await router.close()
        if session is not None:
            # Temporary sessions are always cleaned up (no leakage); persistent
            # sessions stay on disk (never destroyed accidentally here).
            if not session.persistent:
                sctx.destroy(session.id)
            else:
                sctx.expire_stale()
    summary = routed.summary()
    if session_trace is not None:
        summary["session"] = session_trace
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None, default=str))
    return 0 if routed.result.records else 2


def main() -> int:
    return asyncio.run(_run_cli(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

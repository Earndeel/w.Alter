"""Lot 3 — Capability engine: fast-path execution of learned site operations.

Turns frequently-used journeys into virtual APIs:

    request
      → known capability?  (ProfileIndex.lookup_capability, no LLM)
      ├─ yes + confident     → execute recipe (API replay or learned route)
      ├─ yes + medium        → cheap probe / replay attempt
      ├─ yes + broken        → generic Walter Browse → auto-repair (vNext)
      └─ no                  → generic Walter Browse (discovery will learn)

Every execution produces an observation (success/failure, latency, score),
updates capability confidence, and fills the result cache (DATA plane).
No LLM call exists anywhere in this path.
"""
from __future__ import annotations

import time
from typing import Any, Mapping

from profile_index import ProfileIndex, capability_name_from_spec
from result_cache import ResultCache
from universal_extractor import ExtractionResult, ExtractionSpec
from universal_router import UniversalRouter

HIGH_CONFIDENCE = 0.85
LOW_CONFIDENCE = 0.55


class CapabilityResult:
    """Compact output of a capability execution (virtual API response)."""

    def __init__(
        self,
        *,
        capability: str,
        host: str,
        route: str,
        fresh: bool,
        records: list[dict[str, Any]],
        score: float,
        elapsed_s: float,
        cached: bool = False,
        error: str | None = None,
        url: str | None = None,
    ) -> None:
        self.capability = capability
        self.host = host
        self.route = route
        self.fresh = fresh
        self.records = records
        self.score = score
        self.elapsed_s = elapsed_s
        self.cached = cached
        self.error = error
        self.url = url

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "source": self.host,
            "route": self.route,
            "fresh": self.fresh,
            "cached": self.cached,
            "elapsed_s": self.elapsed_s,
            "score": self.score,
            "records": self.records,
            "error": self.error,
        }


class CapabilityEngine:
    """Executes capabilities with the learned recipe, falling back to generic
    browse for unknown/broken ones (auto-repair path)."""

    def __init__(
        self,
        router: UniversalRouter,
        *,
        index: ProfileIndex | None = None,
        cache: ResultCache | None = None,
        high_confidence: float = HIGH_CONFIDENCE,
        low_confidence: float = LOW_CONFIDENCE,
    ) -> None:
        self.router = router
        self.index = index or ProfileIndex()
        self.cache = cache or ResultCache()
        self.high = high_confidence
        self.low = low_confidence

    # -- public API --------------------------------------------------------

    async def execute(
        self,
        host: str,
        capability: str,
        inputs: Mapping[str, Any] | None = None,
        *,
        spec: ExtractionSpec | None = None,
        url: str | None = None,
        mode: str = "auto",
        session: Any = None,
        max_cache_age_s: float | None = None,
        force_fresh: bool = False,
    ) -> CapabilityResult:
        """If NULL CACHE TTLs are used, 'freshness' is informed by the cache.

        Flow: cache (if allowed & fresh) -> learned recipe -> generic fallback.
        """
        cap: dict[str, Any] | None = None
        try:
            cap = self.index.lookup_capability(host, capability)
        except Exception:
            cap = None
        if cap is None:
            return await self._generic(host, capability, inputs, spec=spec, url=url, mode=mode, session=session)
        if (cap.get("implementation") or {}).get("kind") == "conversation":
            # A conversation is never cached: each message is a new exchange (conversation.py).
            return await self._conversation(host, capability, inputs or {})

        params = dict(inputs or {})
        if not force_fresh:
            hit = self.cache.get(host, capability, params)
            if hit is not None and hit.get("fresh"):
                # DATA is fresh: reuse the cached records without re-fetching.
                return CapabilityResult(
                    capability=capability,
                    host=host,
                    route=hit.get("route", "cache"),
                    fresh=True,
                    cached=True,
                    records=self._records_from_cache_entry(hit),
                    score=_safe_score(hit.get("score")),
                    elapsed_s=0.0,
                )

        confidence = float(cap.get("confidence") or 0.0)
        used_url = url
        if used_url is None and cap.get("implementation"):
            used_url = self.router_url_from_implementation(cap, inputs)
        if used_url is None:
            return await self._generic(host, capability, inputs, spec=spec, url=url, mode=mode, session=session)

        spec_for_run = spec
        if spec_for_run is None and cap.get("implementation"):
            spec_for_run = self.spec_from_implementation(cap)
        if spec_for_run is None:
            spec_for_run = _placeholder_spec(capability)

        started = time.perf_counter()
        try:
            routed = await self.router.extract_one(used_url, spec_for_run, mode=mode, session=session)
        except Exception:
            routed = None
        elapsed = time.perf_counter() - started
        records = routed.result.records if routed is not None else []
        score = routed.result.best_candidate.score if routed is not None and routed.result.best_candidate else 0.0
        success = bool(routed is not None and routed.result.valid_candidate_count and records)
        route = routed.route if routed is not None else "failed"

        self.index.observe_capability(
            host,
            capability,
            success=success,
            latency_ms=elapsed * 1000.0,
            score=score,
            record_count=len(records),
        )

        if success:
            self.cache.put(
                host=host,
                capability=capability,
                params=params,
                records=records,
                source_url=used_url,
                route=route,
                extra={"score": round(score, 3)},
            )
            return CapabilityResult(
                capability=capability,
                host=host,
                route=route,
                fresh=True,
                records=records,
                score=score,
                elapsed_s=round(elapsed, 3),
                url=used_url,
            )

        # Capability broke -> generic rediscovery -> repair (new version).
        fallback_url = url
        if fallback_url is None:
            # Re-discover FROM the original page (not the broken recipe URL):
            # the generic router re-learns endpoints on the real journey.
            fallback_url = (cap.get("implementation") or {}).get("page_url") or _url_from_inputs(host, inputs)
        gresult = await self._generic(
            host, capability, inputs, spec=spec_for_run, url=fallback_url, mode=mode, session=session
        )
        if gresult.records:
            self._repair(host, capability, cap, gresult, used_url)
        return gresult

    # -- helpers -----------------------------------------------------------

    async def _conversation(self, host: str, capability: str, inputs: Mapping[str, Any]) -> CapabilityResult:
        import asyncio

        import conversation
        out = await asyncio.to_thread(
            conversation.send, host, capability, str(inputs.get("message") or ""),
            conversation=str(inputs.get("conversation") or "default"), request_id=inputs.get("request_id"),
            session=inputs.get("session"), index=self.index, timeout_s=inputs.get("timeout_s"))
        record = {k: out.get(k) for k in ("reply", "status", "conversation", "request_id", "url", "mode",
                                          "recipe_version", "timings")}
        return CapabilityResult(capability=capability, host=host, route="conversation", fresh=True,
                                records=[record], score=1.0 if out.get("ok") else 0.0,
                                elapsed_s=round((out.get("timings") or {}).get("total_ms", 0) / 1000, 3),
                                error=out.get("error"), url=out.get("url"))

    async def _generic(
        self,
        host: str,
        capability: str,
        inputs: Mapping[str, Any] | None,
        *,
        spec: ExtractionSpec | None,
        url: str | None,
        mode: str,
        session: Any,
    ) -> CapabilityResult:
        started = time.perf_counter()
        spec_for_run = spec or _placeholder_spec(capability)
        used_url = url or _url_from_inputs(host, inputs)
        routed = await self.router.extract_one(used_url, spec_for_run, mode=mode, session=session)
        elapsed = time.perf_counter() - started
        records = routed.result.records if routed is not None else []
        score = routed.result.best_candidate.score if routed is not None and routed.result.best_candidate else 0.0
        success = bool(routed is not None and routed.result.valid_candidate_count and records)
        if success:
            self.index.observe_capability(
                host,
                capability,
                success=True,
                latency_ms=elapsed * 1000.0,
                score=score,
                record_count=len(records),
            )
        return CapabilityResult(
            capability=capability,
            host=host,
            route=routed.route if routed is not None else "failed",
            fresh=True,
            records=records,
            score=score,
            elapsed_s=round(elapsed, 3),
            error=None if success else (routed.result.error if routed is not None else "no route"),
            url=(
                routed.result.best_candidate.url
                if routed is not None and routed.result.best_candidate
                else used_url
            ),
        )

    def _repair(
        self,
        host: str,
        capability: str,
        old: Mapping[str, Any],
        gresult: CapabilityResult,
        failed_url: str,
    ) -> None:
        """A generic run succeeded after the recipe failed: record a new
        implementation so the next request uses the fresh route."""
        try:
            old_impl = old.get("implementation") or {}
            new_impl = dict(old_impl)
            new_impl["route"] = gresult.route
            if gresult.url:
                new_impl["url"] = gresult.url
            new_impl["last_repair_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            new_impl["previous_url"] = failed_url
            self.index.bump_capability_version(
                host,
                capability,
                implementation=new_impl,
                notes=f"route fixed after failure (now {gresult.route})",
            )
        except Exception:
            pass  # repair is best-effort; never breaks the caller

    # -- recipe helpers -----------------------------------------------------

    def router_url_from_implementation(
        self, cap: Mapping[str, Any], inputs: Mapping[str, Any] | None
    ) -> str | None:
        """Render the recipe URL: substitute known inputs for {{key}} slots and
        drop leftover slots so missing inputs never corrupt the request."""
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        impl = cap.get("implementation") or {}
        url = impl.get("url")
        if not url:
            return None
        provided = {str(k): str(v) for k, v in dict(inputs or {}).items() if v is not None}
        if "{{" not in url:
            # No slots: reuse a static learned URL as-is.
            return url
        parsed = urlsplit(str(url))
        query: list[tuple[str, str]] = []
        unused_slot = False
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if "{{" in key or "{{" in value:
                slot = value.strip("{}") if "{{" in value else key.strip("{}")
                if slot in provided:
                    query.append((slot if "{{" in key else key, provided[slot]))
                else:
                    unused_slot = True
            else:
                query.append((key, value))
        # A slot never filled would silently change the endpoint: fall back to
        # the generic path instead of issuing a malformed replay.
        if unused_slot:
            return None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))

    def spec_from_implementation(self, cap: Mapping[str, Any]) -> ExtractionSpec | None:
        impl = cap.get("implementation") or {}
        fields = impl.get("expected_fields")
        if not isinstance(fields, Mapping) or not fields:
            return None
        return ExtractionSpec(
            name=str(cap.get("name") or "capability"),
            expected_fields={str(k): tuple(v) if isinstance(v, (list, tuple)) else (str(v),) for k, v in fields.items()},
            required_fields=tuple(impl.get("required_fields") or list(fields)[:1]),
            min_records=int(impl.get("min_records") or 1),
            score_threshold=float(impl.get("score_threshold") or 25.0),
        )

    def _records_from_cache_entry(self, entry: Mapping[str, Any]) -> list[dict[str, Any]]:
        records = entry.get("records") if isinstance(entry, Mapping) else None
        if isinstance(records, list):
            return [dict(r) for r in records if isinstance(r, Mapping)]
        return []


def _placeholder_spec(name: str) -> ExtractionSpec:
    return ExtractionSpec(
        name="capability:" + name,
        expected_fields={"value": ("value",)},
        required_fields=("value",),
        min_records=1,
        score_threshold=1.0,
    )


def _url_from_inputs(host: str, inputs: Mapping[str, Any] | None) -> str:
    base = f"https://{host}/"
    if not inputs:
        return base
    import urllib.parse

    query = urllib.parse.urlencode({k: str(v) for k, v in inputs.items() if v is not None})
    return base + ("?" + query if query else "")


def _safe_score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
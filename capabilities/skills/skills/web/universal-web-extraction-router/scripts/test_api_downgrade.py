"""Lot 1 tests: signal-aware probe, API discovery + validated HTTP replay
downgrade, and reversible fallback. No LLM anywhere in this path."""
from __future__ import annotations

import asyncio
import json
import time
import unittest

from universal_extractor import (
    ExtractionResult,
    ExtractionSpec,
    ResponseCandidate,
    finalize_extraction_result,
    score_payload,
)
from universal_router import UniversalRouter, _html_utility_ratio, http_probe


class FakeExtractor:
    def __init__(self, result: ExtractionResult) -> None:
        self.result = result
        self.calls = 0
        self.closed = False

    async def extract_one(self, _url: str, _spec: ExtractionSpec) -> ExtractionResult:
        self.calls += 1
        return self.result

    async def replay_one(self, _url, _spec, _template, *, expected_shape_fingerprint=None):
        self.calls += 1
        return self.result

    async def close(self) -> None:
        self.closed = True


class FakeReplayExtractor:
    """extract_one fails on the HTML page; replay_one succeeds on the API."""

    def __init__(self, page_result: ExtractionResult, api_result: ExtractionResult) -> None:
        self.page_result = page_result
        self.api_result = api_result
        self.calls = 0

    async def extract_one(self, _url: str, _spec: ExtractionSpec) -> ExtractionResult:
        self.calls += 1
        return self.page_result

    async def replay_one(self, _url, _spec, _template, *, expected_shape_fingerprint=None, cookies=None):
        self.calls += 1
        return self.api_result


class FakeCamoufox:
    def __init__(self, result: ExtractionResult) -> None:
        self.result = result
        self.calls = 0

    async def extract_one(self, _url: str, _spec: ExtractionSpec) -> ExtractionResult:
        self.calls += 1
        return self.result


def make_result(url: str, spec: ExtractionSpec, payload: object, error: str | None = None) -> ExtractionResult:
    started = time.perf_counter()
    score, matched, record_count = score_payload(payload, spec)
    candidate = ResponseCandidate(
        url=url,
        method="GET",
        status=200,
        content_type="application/json",
        response_bytes=100,
        elapsed_ms=1,
        payload=payload,
        matched_fields=matched,
        record_count=record_count,
        score=score,
    )
    return finalize_extraction_result(url, spec, started, [candidate], error=error)


def make_xhr_result(
    page_url: str,
    api_url: str,
    spec: ExtractionSpec,
    payload: object,
) -> ExtractionResult:
    """A browser result whose data came from a same-site XHR endpoint."""
    started = time.perf_counter()
    score, matched, record_count = score_payload(payload, spec)
    candidate = ResponseCandidate(
        url=api_url,
        method="GET",
        status=200,
        content_type="application/json",
        response_bytes=100,
        elapsed_ms=1,
        payload=payload,
        matched_fields=matched,
        record_count=record_count,
        score=score,
    )
    return finalize_extraction_result(page_url, spec, started, [candidate])


class SignalProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_detects_direct_json_endpoint(self) -> None:
        probe = await http_probe("https://dummyjson.com/products?limit=2")
        self.assertTrue(probe["is_json"])
        self.assertFalse(probe["challenge"])
        self.assertIsNotNone(probe["status"])

    async def test_probe_detects_html_page_as_not_json(self) -> None:
        probe = await http_probe("https://example.com/")
        self.assertFalse(probe["is_json"])
        self.assertEqual(probe["status"], 200)


class ApiDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.page_url = "https://api.test/search"
        self.api_url = "https://api.test/v3/search?query=a"
        self.spec = ExtractionSpec(
            name="flight",
            expected_fields={"price": ("price",), "flight_no": ("flightNo",)},
            required_fields=("price", "flight_no"),
            min_records=1,
            score_threshold=20,
        )
        self.valid_payload = {"results": [{"price": 310, "flightNo": "QR102"}]}

    async def test_discovery_isolates_xhr_endpoints(self) -> None:
        result = make_xhr_result(self.page_url, self.api_url, self.spec, self.valid_payload)
        router = UniversalRouter()
        discovered = router._discover_api_endpoints(result, self.page_url)
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0].url, self.api_url)

    async def test_discovery_ignores_same_url_candidates(self) -> None:
        result = make_result(self.page_url, self.spec, self.valid_payload)
        router = UniversalRouter()
        self.assertEqual(router._discover_api_endpoints(result, self.page_url), [])

    async def test_downgrade_validated_returns_api_replay_route(self) -> None:
        page_result = make_result(self.page_url, self.spec, {"html": {"page": True}}, error="no usable data")
        scrapling = FakeReplayExtractor(
            page_result,
            make_result(self.api_url, self.spec, self.valid_payload),
        )
        browser_result = make_xhr_result(self.page_url, self.api_url, self.spec, self.valid_payload)
        camoufox = FakeCamoufox(browser_result)
        router = UniversalRouter(scrapling_extractor=scrapling, camoufox_client=camoufox)

        routed = await router.extract_one(self.page_url, self.spec)

        self.assertEqual(routed.route, "api-replay")
        self.assertIsNotNone(routed.downgrade)
        self.assertEqual(routed.downgrade["from"], "camoufox-max")
        self.assertTrue(routed.downgrade["validated"])
        self.assertIn("DOWNGRADE_HTTP", routed.trace)
        self.assertIn("API_REPLAY_VALIDATED", routed.trace)
        self.assertEqual(len(routed.result.records), 1)

    async def test_downgrade_failed_keeps_browser_result(self) -> None:
        # Replay returns unusable payload (analytics only) -> keep browser result.
        page_result = make_result(self.page_url, self.spec, {"html": {"page": True}}, error="no usable data")
        scrapling = FakeReplayExtractor(
            page_result,
            make_result(self.api_url, self.spec, {"analytics": {"x": 1}}),
        )
        browser_result = make_xhr_result(self.page_url, self.api_url, self.spec, self.valid_payload)
        camoufox = FakeCamoufox(browser_result)
        router = UniversalRouter(scrapling_extractor=scrapling, camoufox_client=camoufox)

        routed = await router.extract_one(self.page_url, self.spec)

        self.assertEqual(routed.route, "camoufox-max")
        self.assertIsNone(routed.downgrade)
        self.assertIn("API_REPLAY_FAILED", routed.trace)
        self.assertIn("FALLBACK_BROWSER", routed.trace)
        self.assertEqual(len(routed.result.records), 1)

    async def test_auto_json_probe_shortcuts_to_scrapling(self) -> None:
        scrapling = FakeExtractor(make_result(self.page_url, self.spec, self.valid_payload))
        camoufox = FakeCamoufox(make_result(self.page_url, self.spec, self.valid_payload))
        router = UniversalRouter(scrapling_extractor=scrapling, camoufox_client=camoufox)

        routed = await router.extract_one("https://dummyjson.com/products?limit=2", self.spec)

        self.assertEqual(routed.route, "scrapling")
        self.assertEqual(camoufox.calls, 0)
        self.assertIn("API_JSON_DIRECT", routed.trace)


class StaticHtmlFastPathTests(unittest.IsolatedAsyncioTestCase):
    """Non-regression: an exploitable static HTML page must NEVER escalate to
    a browser. The probe body satisfies the contract directly."""

    STATIC_PAGE = """<!DOCTYPE html><html><head><title>Books</title>
<script src="/jquery.min.js"></script></head><body>
<h1>All products</h1>
<ul>
<li class="col-xs-6"><article class="product_pod">
<a href="b.html"><img alt="A Light in the Attic"></a>
<h3><a href="b.html" title="A Light in the Attic">A Light in the Attic</a></h3>
<p class="price_color">£51.77</p></article></li>
<li class="col-xs-6"><article class="product_pod">
<a href="c.html"><img alt="Tipping the Velvet"></a>
<h3><a href="c.html" title="Tipping the Velvet">Tipping the Velvet</a></h3>
<p class="price_color">£53.74</p></article></li>
<li class="col-xs-6"><article class="product_pod">
<a href="d.html"><img alt="Soumission"></a>
<h3><a href="d.html" title="Soumission">Soumission</a></h3>
<p class="price_color">£50.10</p></article></li>
<li class="col-xs-6"><article class="product_pod">
<a href="e.html"><img alt="Sharp Objects"></a>
<h3><a href="e.html" title="Sharp Objects">Sharp Objects</a></h3>
<p class="price_color">£47.82</p></article></li>
<li class="col-xs-6"><article class="product_pod">
<a href="f.html"><img alt="Sapiens"></a>
<h3><a href="f.html" title="Sapiens: A Brief History">Sapiens: A Brief History</a></h3>
<p class="price_color">£54.23</p></article></li>
</ul></body></html>"""

    def setUp(self) -> None:
        self.spec = ExtractionSpec(
            name="books",
            expected_fields={
                "title": ("title", "book", "name"),
                "price": ("price", "price_color", "priceColor"),
            },
            required_fields=("title", "price"),
            min_records=5,
            score_threshold=25,
        )

    async def test_static_html_never_escalates_to_browser(self) -> None:
        """The probe body satisfies the contract: route=static-html, no
        camoufox/webtop calls, no HTTP replay either."""
        spy = _FailOnUseSpyCamoufox()
        webtop = _FailOnUseSpyWebtop()
        scrapling = _FailOnUseSpyScrapling()
        router = UniversalRouter(
            scrapling_extractor=scrapling,
            camoufox_client=spy,
            webtop_client=webtop,
        )

        # Patch http_probe to return our static fixture (no real network in tests).
        import universal_router as mod

        async def fake_probe(url, *, timeout=0.0, content_hints=None):
            body = self.STATIC_PAGE
            return {
                "status": 200,
                "content_type": "text/html",
                "bytes": len(body.encode()),
                "is_json": False,
                "has_scripts": True,
                "html_ratio": _html_utility_ratio(body),
                "looks_spa": False,
                "content_present": True,
                "challenge": False,
                "redirect_target": None,
                "error": None,
                "probe_ms": 5,
                "body": body,
            }

        original = mod.http_probe
        mod.http_probe = fake_probe
        try:
            routed = await router.extract_one("https://books.test/", self.spec)
        finally:
            mod.http_probe = original

        self.assertEqual(routed.route, "static-html")
        self.assertEqual(len(routed.result.records), 5)
        self.assertIn("HTML_STATIC", routed.trace)
        self.assertIn("HTML_STATIC_DIRECT", routed.trace)
        self.assertEqual(scrapling.calls, 0)
        self.assertEqual(spy.calls, 0)
        self.assertEqual(webtop.calls, 0)
        self.assertNotIn("SPA_DETECTED", routed.trace)


class _FailOnUseSpyCamoufox:
    def __init__(self) -> None:
        self.calls = 0

    async def extract_one(self, _url: str, _spec: ExtractionSpec) -> ExtractionResult:
        self.calls += 1
        raise AssertionError("browser must not be used for static HTML")


class _FailOnUseSpyWebtop:
    def __init__(self) -> None:
        self.calls = 0

    async def extract_one(self, _url: str, _spec: ExtractionSpec) -> ExtractionResult:
        self.calls += 1
        raise AssertionError("webtop must not be used for static HTML")


class _FailOnUseSpyScrapling:
    def __init__(self) -> None:
        self.calls = 0

    async def extract_one(self, _url: str, _spec: ExtractionSpec) -> ExtractionResult:
        self.calls += 1
        raise AssertionError("scrapling second fetch must not happen when probe satisfies")


if __name__ == "__main__":
    unittest.main()
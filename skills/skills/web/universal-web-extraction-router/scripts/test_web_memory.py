"""Lot 3 tests: web memory — capabilities, confidence, cache separation,
auto-learning, and the full discover → learn → reuse → break → rediscover →
repair cycle. Zero LLM everywhere."""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path

from capability_engine import CapabilityEngine, CapabilityResult
from profile_index import (
    INDEX_VERSION,
    ProfileIndex,
    _fresh_confidence,
    capability_name_from_spec,
    url_scope,
)
from result_cache import ResultCache
from universal_extractor import (
    ExtractionResult,
    ExtractionSpec,
    ResponseCandidate,
    finalize_extraction_result,
    score_payload,
)
from universal_router import UniversalRouter

ROUTES = ("scrapling", "camoufox-max", "webtop-cdp", "api-replay", "replay", "static-html")


def make_spec(name: str = "product_search") -> ExtractionSpec:
    return ExtractionSpec(
        name=name,
        expected_fields={"title": ("title", "name"), "price": ("price",)},
        required_fields=("title",),
        min_records=1,
        score_threshold=20,
    )


def make_result(url: str, spec: ExtractionSpec, payload: object, route: str = "api-replay") -> ExtractionResult:
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
    result = finalize_extraction_result(url, spec, started, [candidate])
    result.elapsed_s = 0.01
    return result


class FakeRouter:
    """Router stub: returns a configured result and records the route used."""

    def __init__(self) -> None:
        self.result: ExtractionResult | None = None
        self.route = "api-replay"
        self.calls = 0
        self.urls: list[str] = []

    async def extract_one(self, url: str, spec: ExtractionSpec, **kwargs):
        self.calls += 1
        self.urls.append(url)
        if self.result is None:
            raise RuntimeError("no fake result configured")
        return RoutedResultLike(self.result, self.route)


class RoutedResultLike:
    def __init__(self, result: ExtractionResult, route: str) -> None:
        self.result = result
        self.route = route
        self.error = result.error

    def summary(self):
        return self.result.summary()


class WebMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.index = ProfileIndex(path=Path(self.tmp.name) / "profiles.json")
        self.cache = ResultCache(path=Path(self.tmp.name) / "result_cache.json")
        self.router = UniversalRouter(
            scrapling_extractor=None,
            camoufox_client=None,
            webtop_client=None,
            profile_index=self.index,
        )
        self.fake = FakeRouter()

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    # -- capability name inference (zero LLM) ------------------------------

    def test_capability_name_from_operation_spec(self) -> None:
        spec = make_spec("hotel_search")
        scope = url_scope("https://www.booking.com/hotels?dest=paris")
        self.assertEqual(capability_name_from_spec(spec, scope), "hotel_search")

    def test_capability_name_from_path_token(self) -> None:
        spec = make_spec("browse")
        scope = url_scope("https://example.com/api/search?q=test")
        self.assertEqual(capability_name_from_spec(spec, scope), "search")

    def test_no_capability_for_plain_fetch(self) -> None:
        spec = make_spec("homepage")
        scope = url_scope("https://example.com/")
        self.assertEqual(capability_name_from_spec(spec, scope), "")

    # -- domain profile ----------------------------------------------------

    def test_domain_profile_aggregates(self) -> None:
        self.index.observe_domain("https://shop.example.com/products", route="scrapling", success=True, elapsed_s=0.5)
        self.index.observe_domain("https://shop.example.com/products", route="scrapling", success=True, elapsed_s=0.3)
        self.index.observe_domain("https://shop.example.com/products", route="scrapling", success=False, elapsed_s=0.2)
        domain = self.index.domain_profile("shop.example.com")
        self.assertIsNotNone(domain)
        assert domain is not None
        self.assertEqual(domain["successes"], 2)
        self.assertEqual(domain["failures"], 1)
        self.assertEqual(domain["routing"]["preferred"], "scrapling")
        self.assertGreater(domain["routing"]["confidence"], 0.3)

    def test_domain_profile_remembers_endpoints(self) -> None:
        self.index.observe_domain(
            "https://shop.example.com/products",
            route="camoufox-max",
            success=True,
            elapsed_s=0.5,
            endpoint_url="https://api.shop.example.com/v3/search?cat=all",
        )
        domain = self.index.domain_profile("shop.example.com")
        assert domain is not None
        self.assertEqual(len(domain["endpoints"]), 1)
        self.assertEqual(domain["endpoints"][0]["path"], "/v3/search")

    # -- capability registry -----------------------------------------------

    def test_register_and_lookup_capability(self) -> None:
        self.index.register_capability(
            "shop.example.com",
            "product_search",
            inputs={"q": "string"},
            outputs={"title": "string"},
            implementation={"type": "api-replay", "url": "https://api.shop.example.com/search?q={{q}}"},
        )
        cap = self.index.lookup_capability("shop.example.com", "product_search")
        self.assertIsNotNone(cap)
        assert cap is not None
        self.assertEqual(cap["version"], 1)
        self.assertEqual(cap["status"], "proposed")
        self.assertAlmostEqual(cap["confidence"], 0.5, delta=0.01)

    def test_capability_confidence_grows_with_success(self) -> None:
        self.index.register_capability(
            "shop.example.com", "product_search",
            inputs={"q": "string"}, outputs={"title": "string"},
            implementation={"type": "api-replay", "url": "u"},
        )
        for _ in range(5):
            self.index.observe_capability("shop.example.com", "product_search", success=True, latency_ms=120)
        cap = self.index.lookup_capability("shop.example.com", "product_search")
        assert cap is not None
        self.assertGreater(cap["confidence"], 0.6)
        self.assertEqual(cap["status"], "active")

    def test_capability_degrades_with_failures(self) -> None:
        self.index.register_capability(
            "shop.example.com", "product_search",
            inputs={"q": "string"}, outputs={"title": "string"},
            implementation={"type": "api-replay", "url": "u"},
        )
        for _ in range(3):
            self.index.observe_capability("shop.example.com", "product_search", success=False, latency_ms=800)
        cap = self.index.lookup_capability("shop.example.com", "product_search")
        assert cap is not None
        self.assertLess(cap["confidence"], 0.5)
        self.assertEqual(cap["status"], "degraded")

    def test_confidence_decays_with_age(self) -> None:
        old = _fresh_confidence(
            base=0.5, successes=10, failures=0,
            last_verified_epoch=time.time() - 40 * 24 * 3600,
            now_epoch=time.time(),
        )
        fresh = _fresh_confidence(
            base=0.5, successes=10, failures=0,
            last_verified_epoch=time.time(),
            now_epoch=time.time(),
        )
        self.assertLess(old, fresh)

    def test_version_bump_keeps_history(self) -> None:
        self.index.register_capability(
            "shop.example.com", "product_search",
            inputs={"q": "string"}, outputs={"title": "string"},
            implementation={"type": "api-replay", "url": "https://old.example.com/v1/search"},
        )
        bumped = self.index.bump_capability_version(
            "shop.example.com", "product_search",
            implementation={"type": "api-replay", "url": "https://old.example.com/v2/search"},
            notes="endpoint changed",
        )
        assert bumped is not None
        self.assertEqual(bumped["version"], 2)
        self.assertEqual(len(bumped["versions"]), 2)
        cap = self.index.lookup_capability("shop.example.com", "product_search")
        assert cap is not None
        self.assertEqual(cap["implementation"]["url"], "https://old.example.com/v2/search")
        self.assertEqual(cap["failures"], 0)  # repaired

    # -- result cache (DATA plane) -----------------------------------------

    def test_cache_roundtrip_and_freshness(self) -> None:
        key = self.cache.put(
            host="shop.example.com",
            capability="product_search",
            params={"q": "laptop"},
            records=[{"title": "X1", "price": 9}],
            source_url="https://shop.example.com/s?q=laptop",
            route="api-replay",
        )
        hit = self.cache.get("shop.example.com", "product_search", {"q": "laptop"})
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertTrue(hit["fresh"])
        self.assertEqual(hit["record_count"], 1)
        self.assertEqual(len(hit["records"]), 1)
        miss = self.cache.get("shop.example.com", "product_search", {"q": "other"})
        self.assertIsNone(miss)

    def test_cache_expiry(self) -> None:
        self.cache.put(
            host="shop.example.com", capability="product_search", params={},
            records=[{"title": "A"}], source_url="u", route="api-replay",
            ttl_seconds=0.01,
        )
        time.sleep(0.03)
        hit = self.cache.get("shop.example.com", "product_search", {})
        assert hit is not None
        self.assertFalse(hit["fresh"])  # data expired

    def test_knowledge_and_data_are_separate_files(self) -> None:
        # knowledge goes to profiles.json, data to result_cache.json
        self.index.register_capability(
            "shop.example.com", "product_search",
            inputs={}, outputs={}, implementation={"type": "api-replay", "url": "u"},
        )
        self.cache.put(
            host="shop.example.com", capability="product_search", params={},
            records=[{"title": "A"}], source_url="u", route="api-replay",
        )
        self.assertIn("capabilities", json.loads(Path(self.tmp.name).read_text() if False else Path(self.index.path).read_text()))
        cache_payload = json.loads(Path(self.cache.path).read_text())
        self.assertIn("entries", cache_payload)
        self.assertNotIn("capabilities", cache_payload)

    # -- engine fast path ---------------------------------------------------

    async def test_unknown_capability_falls_back_to_generic(self) -> None:
        self.fake.result = make_result("https://unknown.test/", make_spec(), {"results": [{"title": "x"}]})
        engine = CapabilityEngine(self.fake, index=self.index, cache=self.cache)
        result = await engine.execute("unknown.test", "product_search", {"q": "x"})
        self.assertTrue(result.records)
        self.assertEqual(self.fake.calls, 1)
        self.assertEqual(result.route, "api-replay")

    async def test_known_capability_uses_cached_records(self) -> None:
        self.index.register_capability(
            "shop.example.com", "product_search",
            inputs={"q": "string"}, outputs={"title": "string"},
            implementation={"type": "api-replay", "url": "https://api.shop.example.com/search?q={{q}}"},
        )
        self.cache.put(
            host="shop.example.com", capability="product_search", params={"q": "laptop"},
            records=[{"title": "X1", "price": 19}],
            source_url="u", route="api-replay",
        )
        engine = CapabilityEngine(self.fake, index=self.index, cache=self.cache)
        result = await engine.execute("shop.example.com", "product_search", {"q": "laptop"})
        self.assertTrue(result.cached)
        self.assertEqual(result.records[0]["title"], "X1")
        self.assertEqual(self.fake.calls, 0)  # no network at all

    async def test_capability_recipe_execution_records_observation(self) -> None:
        self.index.register_capability(
            "shop.example.com", "product_search",
            inputs={"q": "string"}, outputs={"title": "string"},
            implementation={
                "type": "api-replay",
                "url": "https://shop.example.com/search?q={{q}}",
                "expected_fields": {"title": ["title", "name"]},
                "required_fields": ["title"],
            },
        )
        self.fake.result = make_result(
            "https://shop.example.com/search?q=laptop", make_spec(),
            {"results": [{"title": "Y1", "price": 5}]},
        )
        engine = CapabilityEngine(self.fake, index=self.index, cache=self.cache)
        result = await engine.execute("shop.example.com", "product_search", {"q": "laptop"})
        self.assertTrue(result.records)
        cap = self.index.lookup_capability("shop.example.com", "product_search")
        assert cap is not None
        self.assertEqual(cap["successes"], 1)
        self.assertGreater(cap["confidence"], 0.5)
        # The successful data went into the cache (DATA plane).
        hit = self.cache.get("shop.example.com", "product_search", {"q": "laptop"})
        self.assertIsNotNone(hit)

    async def test_break_then_rediscover_then_repair_cycle(self) -> None:
        """The full Lot 3 cycle on one journey."""
        host, name = "shop.example.com", "product_search"
        # v1 learned recipe.
        self.index.register_capability(
            host, name,
            inputs={"q": "string"}, outputs={"title": "string"},
            implementation={
                "type": "api-replay",
                "url": "https://shop.example.com/v1/search?q={{q}}",
                "expected_fields": {"title": ["title"]},
                "required_fields": ["title"],
            },
        )
        for _ in range(3):
            self.index.observe_capability(host, name, success=True, latency_ms=100)
        # BROKEN: the v1 endpoint now 404s; generic browse discovers v2.
        class BrokenThenFixedRouter(FakeRouter):
            def __init__(self) -> None:
                super().__init__()
                self.failed = False

            async def extract_one(self, url: str, spec: ExtractionSpec, **kwargs):
                self.calls += 1
                self.urls.append(url)
                if "/v1/" in url and not self.failed:
                    self.failed = True
                    raise RuntimeError("404 v1 endpoint gone")
                self.result = make_result(
                    "https://shop.example.com/v2/search?q=laptop", spec,
                    {"results": [{"title": "NewV2", "price": 42}]},
                )
                self.route = "api-replay"
                return RoutedResultLike(self.result, self.route)

        broken = BrokenThenFixedRouter()
        engine = CapabilityEngine(broken, index=self.index, cache=self.cache)
        result = await engine.execute(host, name, {"q": "laptop"})
        self.assertTrue(result.records)
        self.assertEqual(result.records[0]["title"], "NewV2")
        # REPAIR: the capability was bumped to v2 with the new route.
        cap = self.index.lookup_capability(host, name)
        assert cap is not None
        self.assertEqual(cap["version"], 2)
        self.assertEqual(cap["status"], "active")
        self.assertIn("v2", cap["implementation"]["url"])


if __name__ == "__main__":
    unittest.main()
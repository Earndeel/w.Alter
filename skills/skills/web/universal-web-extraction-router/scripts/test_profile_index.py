from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from profile_index import (
    INDEX_VERSION,
    ProfileIndex,
    build_replay_template,
    profile_key,
    render_replay_url,
)
from universal_extractor import (
    ExtractionResult,
    ExtractionSpec,
    ResponseCandidate,
    finalize_extraction_result,
    score_payload,
)
from universal_router import UniversalRouter


class FakeBackend:
    def __init__(self, result: ExtractionResult) -> None:
        self.result = result
        self.calls = 0
        self.replay_calls = 0

    async def extract_one(self, _url: str, _spec: ExtractionSpec) -> ExtractionResult:
        self.calls += 1
        return self.result

    async def replay_one(self, _url: str, _spec: ExtractionSpec, _template, **_kwargs) -> ExtractionResult:
        self.replay_calls += 1
        return self.result

    async def close(self) -> None:
        return None


def make_spec() -> ExtractionSpec:
    return ExtractionSpec(
        name="flight-search",
        expected_fields={"price": ("price",), "flight_no": ("flightNo",)},
        required_fields=("price", "flight_no"),
        min_records=1,
        score_threshold=20,
    )


def make_result(url: str, spec: ExtractionSpec, payload: object, method: str = "GET") -> ExtractionResult:
    started = time.perf_counter()
    score, matched, record_count = score_payload(payload, spec)
    candidate = ResponseCandidate(
        url=url,
        method=method,
        status=200,
        content_type="application/json",
        response_bytes=100,
        elapsed_ms=1,
        payload=payload,
        matched_fields=matched,
        record_count=record_count,
        score=score,
    )
    return finalize_extraction_result(url, spec, started, [candidate])


class ProfileIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "profiles.json"
        self.url = "https://www.trip.com/flights/showfarefirst?dcity=gva&acity=bkk&ddate=2026-09-25"
        self.spec = make_spec()
        self.valid = make_result(self.url, self.spec, {"results": [{"price": 310, "flightNo": "QR102"}]})
        self.invalid = make_result(self.url, self.spec, {"analytics": {"event": "page_view"}})

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dynamic_values_share_one_profile_key(self) -> None:
        later_url = self.url.replace("2026-09-25", "2026-12-01")
        self.assertEqual(profile_key(self.url, self.spec), profile_key(later_url, self.spec))

    def test_get_json_candidate_builds_a_safe_parameterized_replay_template(self) -> None:
        source_url = "https://www.trip.com/flights?dcity=gva&ddate=2026-09-25&curr=EUR"
        candidate_url = (
            "https://api.trip.com/search?dcity=gva&ddate=2026-09-25"
            "&currency=EUR&locale=en_xx"
        )

        template = build_replay_template(
            source_url,
            candidate_url,
            method="GET",
            content_type="application/json",
            dynamic_query_keys=("dcity", "ddate"),
        )

        self.assertIsNotNone(template)
        assert template is not None
        replay_url = render_replay_url(
            template,
            "https://www.trip.com/flights?dcity=par&ddate=2026-12-01&curr=USD",
        )
        self.assertIn("dcity=par", replay_url)
        self.assertIn("ddate=2026-12-01", replay_url)
        self.assertIn("currency=EUR", replay_url)
        self.assertIn("locale=en_xx", replay_url)

        self.assertIsNone(
            build_replay_template(
                source_url,
                candidate_url + "&access_token=secret",
                method="GET",
                content_type="application/json",
                dynamic_query_keys=("dcity", "ddate"),
            )
        )

    def test_success_is_persisted_as_a_safe_route_profile(self) -> None:
        index = ProfileIndex(self.path)
        index.observe(
            self.url,
            self.spec,
            route="webtop-cdp",
            result=self.valid,
            attempts=[
                {"backend": "scrapling", "usable": False},
                {"backend": "camoufox-max", "usable": False},
                {"backend": "webtop-cdp", "usable": True},
            ],
        )

        reloaded = ProfileIndex(self.path)
        hit = reloaded.lookup(self.url.replace("2026-09-25", "2026-12-01"), self.spec)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.preferred_route, "replay")
        self.assertEqual(hit.entry["preferred_route"], "webtop-cdp")
        self.assertTrue(hit.fresh)
        self.assertEqual(hit.entry["success_count"], 1)
        self.assertEqual(reloaded.stats()["profile_count"], 1)

        stored = json.loads(self.path.read_text(encoding="utf-8"))
        raw = self.path.read_text(encoding="utf-8")
        self.assertNotIn('"payload"', raw)
        self.assertNotIn("QR102", raw)
        self.assertNotIn("cookies", raw.lower())
        self.assertNotIn("authorization", raw.lower())
        self.assertEqual(stored["version"], INDEX_VERSION)
        self.assertIn("candidate", next(iter(stored["profiles"].values())))

    def test_confirmed_shape_drift_disables_replay_until_it_relearns(self) -> None:
        index = ProfileIndex(self.path)
        changed_shape = make_result(
            self.url,
            self.spec,
            {"journeys": [{"price": 310, "flightNo": "QR102"}]},
        )
        index.observe(self.url, self.spec, route="scrapling", result=self.valid)
        index.observe(self.url, self.spec, route="scrapling", result=changed_shape)
        index.observe(self.url, self.spec, route="scrapling", result=changed_shape)

        hit = index.lookup(self.url, self.spec)

        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.entry["schema_status"], "drifted")
        self.assertEqual(hit.entry["schema_drift_count"], 1)
        self.assertFalse(hit.entry["replay_enabled"])
        self.assertFalse(hit.summary()["replay_available"])

    def test_query_shape_variation_can_reuse_same_path_profile(self) -> None:
        index = ProfileIndex(self.path)
        index.observe(self.url, self.spec, route="scrapling", result=self.valid)
        changed_query = "https://trip.com/flights/showfarefirst?dcity=gva&acity=bkk&ddate=2026-12-01&sort=price"

        hit = index.lookup(changed_query, self.spec)

        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.match, "path")
        self.assertEqual(hit.preferred_route, "replay")
        index.observe(changed_query, self.spec, route="scrapling", result=self.valid)
        self.assertEqual(index.stats()["profile_count"], 1)

    def test_stale_profile_is_visible_but_never_shortcuts_the_router(self) -> None:
        index = ProfileIndex(self.path, ttl_seconds=0.001, max_age_seconds=60)
        index.observe(self.url, self.spec, route="camoufox-max", result=self.valid)
        time.sleep(0.01)

        hit = index.lookup(self.url, self.spec)

        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertFalse(hit.fresh)
        self.assertIsNone(hit.preferred_route)
        self.assertTrue(hit.summary()["stale"])

    def test_two_failures_degrade_a_profile_and_a_later_success_recovers_it(self) -> None:
        index = ProfileIndex(self.path)
        index.observe(self.url, self.spec, route="webtop-cdp", result=self.valid)
        index.observe(
            self.url,
            self.spec,
            route="webtop-cdp",
            result=self.invalid,
            attempts=[{"backend": "webtop-cdp", "usable": False}],
        )
        index.observe(
            self.url,
            self.spec,
            route="webtop-cdp",
            result=self.invalid,
            attempts=[{"backend": "webtop-cdp", "usable": False}],
        )

        degraded = index.lookup(self.url, self.spec)
        self.assertIsNotNone(degraded)
        assert degraded is not None
        self.assertEqual(degraded.entry["status"], "degraded")
        self.assertIsNone(degraded.preferred_route)

        index.observe(self.url, self.spec, route="scrapling", result=self.valid)
        recovered = index.lookup(self.url, self.spec)
        self.assertIsNotNone(recovered)
        assert recovered is not None
        self.assertEqual(recovered.preferred_route, "replay")
        self.assertEqual(recovered.entry["failure_streak"], 0)

    def test_invalidation_accepts_a_query_shape_variant(self) -> None:
        index = ProfileIndex(self.path)
        original_url = "https://example.test/results?query=travel"
        variant_url = "https://example.test/results?query=aviation&sort=recent"
        index.observe(original_url, self.spec, route="scrapling", result=self.valid)

        self.assertTrue(index.invalidate(variant_url, self.spec, reason="site changed"))
        hit = index.lookup(original_url, self.spec)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.entry["status"], "invalidated")
        self.assertIsNone(hit.preferred_route)

    def test_corrupt_storage_is_non_fatal_and_can_be_repaired(self) -> None:
        self.path.write_text("{not-json", encoding="utf-8")
        index = ProfileIndex(self.path)

        self.assertIsNone(index.lookup(self.url, self.spec))
        self.assertIsNotNone(index.stats()["load_error"])

        index.observe(self.url, self.spec, route="scrapling", result=self.valid)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["version"], INDEX_VERSION)


class IndexedRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_replay_template_is_tried_before_browser_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            url = "https://example.test/results?day=1"
            spec = make_spec()
            valid = make_result(
                "https://api.example.test/search?day=1&format=json",
                spec,
                {"results": [{"price": 310, "flightNo": "QR102"}]},
            )
            index = ProfileIndex(path)
            index.observe(url, spec, route="scrapling", result=valid)
            scrapling = FakeBackend(valid)
            camoufox = FakeBackend(valid)
            webtop = FakeBackend(valid)
            router = UniversalRouter(
                scrapling_extractor=scrapling,
                camoufox_client=camoufox,
                webtop_client=webtop,
                profile_index=index,
            )

            routed = await router.extract_one(
                url.replace("day=1", "day=2"),
                spec,
            )

            self.assertEqual(routed.route, "replay")
            self.assertEqual(scrapling.replay_calls, 1)
            self.assertEqual(scrapling.calls, 0)
            self.assertEqual(camoufox.calls, 0)
            self.assertTrue(routed.profile["replayed"])
            await router.close()

    async def test_fresh_profile_moves_the_known_backend_to_the_front(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            url = "https://example.test/results?day=1"
            spec = make_spec()
            valid = make_result(
                url,
                spec,
                {"results": [{"price": 310, "flightNo": "QR102"}]},
                method="POST",
            )
            index = ProfileIndex(path)
            index.observe(url, spec, route="webtop-cdp", result=valid)
            scrapling = FakeBackend(valid)
            camoufox = FakeBackend(valid)
            webtop = FakeBackend(valid)
            router = UniversalRouter(
                scrapling_extractor=scrapling,
                camoufox_client=camoufox,
                webtop_client=webtop,
                profile_index=index,
            )

            routed = await router.extract_one(url.replace("day=1", "day=2"), spec)

            self.assertEqual(routed.route, "webtop-cdp")
            self.assertEqual(webtop.calls, 1)
            self.assertEqual(scrapling.calls, 0)
            self.assertEqual(camoufox.calls, 0)
            self.assertEqual(routed.profile["preferred_route"], "webtop-cdp")
            self.assertEqual(routed.profile["route_used"], "webtop-cdp")
            self.assertFalse(routed.profile["relearned"])
            await router.close()

    async def test_failed_hint_falls_back_and_relearns_the_successful_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            url = "https://example.test/results"
            spec = make_spec()
            valid = make_result(
                url,
                spec,
                {"results": [{"price": 310, "flightNo": "QR102"}]},
                method="POST",
            )
            invalid = make_result(url, spec, {"analytics": {"event": "page_view"}})
            index = ProfileIndex(path)
            index.observe(url, spec, route="webtop-cdp", result=valid)
            scrapling = FakeBackend(valid)
            camoufox = FakeBackend(invalid)
            webtop = FakeBackend(invalid)
            router = UniversalRouter(
                scrapling_extractor=scrapling,
                camoufox_client=camoufox,
                webtop_client=webtop,
                profile_index=index,
            )

            routed = await router.extract_one(url, spec)

            self.assertEqual(routed.route, "scrapling")
            self.assertEqual([item["backend"] for item in routed.attempts], ["webtop-cdp", "scrapling"])
            self.assertEqual(routed.profile["route_used"], "scrapling")
            self.assertEqual(routed.profile["route_learned"], "scrapling")
            self.assertTrue(routed.profile["relearned"])
            learned = index.lookup(url, spec)
            self.assertIsNotNone(learned)
            assert learned is not None
            self.assertEqual(learned.preferred_route, "scrapling")
            await router.close()


if __name__ == "__main__":
    unittest.main()

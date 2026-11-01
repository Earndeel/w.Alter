from __future__ import annotations

import time
import unittest

from universal_extractor import (
    ExtractionResult,
    ExtractionSpec,
    ResponseCandidate,
    finalize_extraction_result,
    score_payload,
)
from universal_router import CamoufoxMaxClient, UniversalRouter
from webtop_client import WebtopCdpClient, normalize_trip_hotel_detail_payload


class FakeExtractor:
    def __init__(self, result: ExtractionResult) -> None:
        self.result = result
        self.calls = 0
        self.closed = False

    async def extract_one(self, _url: str, _spec: ExtractionSpec) -> ExtractionResult:
        self.calls += 1
        return self.result

    async def close(self) -> None:
        self.closed = True


class FakeCamoufox:
    def __init__(self, result: ExtractionResult) -> None:
        self.result = result
        self.calls = 0

    async def extract_one(self, _url: str, _spec: ExtractionSpec) -> ExtractionResult:
        self.calls += 1
        return self.result


class FakeWebtop(FakeCamoufox):
    pass


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


class UniversalRouterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.url = "https://example.test/api/results"
        self.spec = ExtractionSpec(
            name="flight",
            expected_fields={
                "price": ("price",),
                "flight_no": ("flightNo",),
            },
            required_fields=("price", "flight_no"),
            min_records=1,
            score_threshold=20,
        )
        self.valid_payload = {"results": [{"price": 310, "flightNo": "QR102"}]}
        self.invalid_payload = {"analytics": {"event": "page_view"}}

    async def test_auto_stops_at_usable_scrapling_result(self) -> None:
        scrapling = FakeExtractor(make_result(self.url, self.spec, self.valid_payload))
        camoufox = FakeCamoufox(make_result(self.url, self.spec, self.valid_payload))
        router = UniversalRouter(scrapling_extractor=scrapling, camoufox_client=camoufox)

        routed = await router.extract_one(self.url, self.spec)

        self.assertEqual(routed.route, "scrapling")
        self.assertEqual(len(routed.result.records), 1)
        self.assertEqual(camoufox.calls, 0)
        self.assertTrue(routed.attempts[0]["usable"])

    async def test_auto_falls_back_to_camoufox_when_scrapling_is_empty(self) -> None:
        scrapling = FakeExtractor(make_result(self.url, self.spec, self.invalid_payload))
        camoufox = FakeCamoufox(make_result(self.url, self.spec, self.valid_payload))
        router = UniversalRouter(scrapling_extractor=scrapling, camoufox_client=camoufox)

        routed = await router.extract_one(self.url, self.spec)

        self.assertEqual(routed.route, "camoufox-max")
        self.assertEqual(len(routed.attempts), 2)
        self.assertEqual(camoufox.calls, 1)
        self.assertEqual(routed.result.records[0]["flight_no"], "QR102")

    async def test_auto_recommends_webtop_when_both_backends_fail_semantically(self) -> None:
        scrapling = FakeExtractor(make_result(self.url, self.spec, self.invalid_payload))
        camoufox = FakeCamoufox(make_result(self.url, self.spec, self.invalid_payload))
        router = UniversalRouter(scrapling_extractor=scrapling, camoufox_client=camoufox)

        routed = await router.extract_one(self.url, self.spec)

        self.assertEqual(routed.route, "camoufox-max")
        self.assertEqual(routed.escalation["recommended_backend"], "webtop-cdp")
        self.assertFalse(routed.attempts[-1]["usable"])

    async def test_auto_uses_webtop_when_it_is_configured(self) -> None:
        scrapling = FakeExtractor(make_result(self.url, self.spec, self.invalid_payload))
        camoufox = FakeCamoufox(make_result(self.url, self.spec, self.invalid_payload))
        webtop = FakeWebtop(make_result(self.url, self.spec, self.valid_payload))
        router = UniversalRouter(
            scrapling_extractor=scrapling,
            camoufox_client=camoufox,
            webtop_client=webtop,
        )

        routed = await router.extract_one(self.url, self.spec)

        self.assertEqual(routed.route, "webtop-cdp")
        self.assertEqual(len(routed.attempts), 3)
        self.assertEqual(webtop.calls, 1)
        self.assertEqual(routed.result.records[0]["flight_no"], "QR102")


class CamoufoxMaxClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_contract_uses_init_script_and_closes_tab(self) -> None:
        url = "https://example.test/api/results"
        spec = ExtractionSpec(
            expected_fields={"price": ("price",), "flight_no": ("flightNo",)},
            required_fields=("price", "flight_no"),
            min_records=1,
            score_threshold=20,
        )
        calls: list[tuple[str, str, dict | None]] = []

        def request(method: str, path: str, payload: dict | None) -> dict:
            calls.append((method, path, payload))
            if path == "/tab/new":
                return {"ok": True, "tabId": "tab-1"}
            if path == "/tab/network-captures":
                return {
                    "ok": True,
                    "captures": [
                        {
                            "url": url,
                            "method": "GET",
                            "status": 200,
                            "contentType": "application/json",
                            "payload": {"results": [{"price": 310, "flightNo": "QR102"}]},
                        }
                    ],
                }
            if path == "/tab/evaluate" and payload and "__UNIVERSAL_CAPTURE__" in payload["expression"]:
                return {
                    "ok": True,
                    "result": [
                        {
                            "url": url,
                            "method": "GET",
                            "status": 200,
                            "contentType": "application/json",
                            "payload": {"results": [{"price": 310, "flightNo": "QR102"}]},
                        }
                    ],
                }
            if path == "/tab/evaluate":
                return {"ok": True, "result": {"htmlBytes": 123, "payload": None}}
            return {"ok": True}

        client = CamoufoxMaxClient(
            request_fn=request,
            capture_wait_seconds=0.5,
        )
        result = await client.extract_one(url, spec)

        paths = [path for _, path, _ in calls]
        self.assertEqual(paths[:3], ["/tab/new", "/tab/add-init-script", "/tab/navigate"])
        self.assertIn("/tab/close", paths)
        self.assertEqual(result.records[0]["price"], 310)
        self.assertIsNone(result.error)


class WebtopCdpClientTests(unittest.TestCase):
    def test_trip_detail_normalizer_expands_room_rows_with_hotel_context(self) -> None:
        normalized = normalize_trip_hotel_detail_payload(
            {
                "hotel": {
                    "hotelName": "Siam Riverside House",
                    "hotelId": "105",
                    "hotelUrl": "https://www.trip.com/hotels/detail/?hotelId=105",
                    "reviewRating": "4.7/5",
                    "address": "Charoen Nakhon, Bangkok",
                },
                "rooms": [
                    {
                        "roomName": "Deluxe King",
                        "price": "EUR 84",
                        "total": "EUR 99",
                        "available": True,
                        "roomsLeft": "3",
                    },
                    {
                        "roomName": "River View Suite",
                        "roomPrice": "126 EUR",
                        "soldOut": True,
                    },
                ],
            }
        )

        records = normalized["hotelResults"]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["hotelName"], "Siam Riverside House")
        self.assertEqual(records[0]["roomType"], "Deluxe King")
        self.assertEqual(records[0]["totalPrice"], 99.0)
        self.assertEqual(records[0]["priceBasis"], "total")
        self.assertTrue(records[0]["available"])
        self.assertEqual(records[1]["nightlyPrice"], 126.0)
        self.assertEqual(records[1]["priceBasis"], "nightly")
        self.assertFalse(records[1]["available"])

    def test_local_cdp_port_fallback_is_bounded_and_deterministic(self) -> None:
        self.assertEqual(
            WebtopCdpClient(cdp_url="http://127.0.0.1:9223")._cdp_urls(),
            ("http://127.0.0.1:9223", "http://127.0.0.1:9222"),
        )
        self.assertEqual(
            WebtopCdpClient(cdp_url="http://example.test:9223")._cdp_urls(),
            ("http://example.test:9223",),
        )


if __name__ == "__main__":
    unittest.main()

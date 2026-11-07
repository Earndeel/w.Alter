from __future__ import annotations

import unittest

from universal_extractor import (
    ExtractionSpec,
    PersistentSessionPool,
    UniversalExtractor,
    is_json_response_candidate,
    meets_spec,
    project_records,
    score_payload,
)
from profile_index import build_replay_template


class UniversalExtractorUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = ExtractionSpec(
            expected_fields={
                "price": ("totalPrice", "price"),
                "duration": ("duration",),
                "flight_no": ("flightNo",),
                "airport_code": ("airportCode",),
            },
            required_fields=("price", "flight_no"),
            min_records=2,
            score_threshold=20,
        )

    def test_scores_nested_payload_without_endpoint_knowledge(self) -> None:
        payload = {
            "journeyList": [
                {
                    "duration": 955,
                    "totalPrice": 310,
                    "transportList": [{"flight": {"flightNo": "QR102", "airportCode": "GVA"}}],
                },
                {
                    "duration": 960,
                    "totalPrice": 315,
                    "transportList": [{"flight": {"flightNo": "QR103", "airportCode": "GVA"}}],
                },
            ]
        }
        score, matched, record_count = score_payload(payload, self.spec)
        self.assertGreaterEqual(score, self.spec.score_threshold)
        self.assertEqual(set(matched), {"airport_code", "duration", "flight_no", "price"})
        self.assertEqual(record_count, 2)

    def test_projects_records_and_keeps_source_paths(self) -> None:
        payload = {
            "results": [
                {"price": 310, "duration": 955, "flightNo": "QR102", "airportCode": "GVA"},
                {"price": 315, "duration": 960, "flightNo": "QR103", "airportCode": "GVA"},
            ]
        }
        records = project_records(payload, self.spec)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["price"], 310)
        self.assertEqual(records[0]["flight_no"], "QR102")
        self.assertEqual(records[0]["airport_code"], "GVA")
        self.assertEqual(records[0]["_source_path"], "results")

    def test_irrelevant_analytics_payload_scores_low(self) -> None:
        payload = {"event": "page_view", "sessionId": "opaque", "items": []}
        score, matched, record_count = score_payload(payload, self.spec)
        self.assertEqual(score, 0)
        self.assertEqual(matched, ())
        self.assertEqual(record_count, 0)

    def test_large_partial_payload_is_not_semantically_valid(self) -> None:
        payload = {"calendar": [{"price": 310} for _ in range(100)]}
        score, matched, record_count = score_payload(payload, self.spec)
        self.assertGreater(score, 0)
        self.assertFalse(meets_spec(matched, record_count, self.spec))

    def test_single_record_can_use_unambiguous_payload_context(self) -> None:
        payload = {
            "journeyList": [{"duration": 955, "flightNo": "QR102", "airportCode": "GVA"}],
            "accurateTotalPrice": 310,
        }
        records = project_records(payload, self.spec)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["price"], 310)
        self.assertTrue(records[0]["_price_path"].startswith("$context."))

    def test_single_object_answer_is_one_record_only_when_it_carries_the_ask(self) -> None:
        spec = ExtractionSpec(expected_fields={"amount": ("amount",), "base": ("base",), "currency": ("currency",)})
        spot = {"data": {"amount": "67950.1", "base": "BTC", "currency": "EUR"}}
        _, matched, count = score_payload(spot, spec)
        self.assertEqual(count, 1)
        self.assertTrue(meets_spec(matched, count, spec))
        self.assertEqual(project_records(spot, spec)[0]["amount"], "67950.1")
        stray = {"consent": {"currency": "EUR", "vendors": 412}}
        _, matched, count = score_payload(stray, spec)
        self.assertEqual(count, 0)
        self.assertFalse(meets_spec(matched, count, self.spec))

    def test_json_capture_accepts_direct_api_documents_but_not_html(self) -> None:
        self.assertTrue(is_json_response_candidate("document", "application/json"))
        self.assertTrue(is_json_response_candidate("xhr", "application/json; charset=utf-8"))
        self.assertTrue(is_json_response_candidate("fetch", "application/json"))
        self.assertFalse(is_json_response_candidate("document", "text/html"))
        self.assertFalse(is_json_response_candidate("image", "application/json"))


class PersistentSessionPoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_one_session_per_domain_and_closes_each_session(self) -> None:
        created = []

        class FakeSession:
            def __init__(self, **_kwargs):
                self.fetches = []
                self.closed = False

            async def start(self):
                return None

            async def fetch(self, url, **_kwargs):
                self.fetches.append(url)
                return url

            async def close(self):
                self.closed = True

        def factory(**kwargs):
            session = FakeSession(**kwargs)
            created.append(session)
            return session

        pool = PersistentSessionPool(session_factory=factory, max_pages=2)
        try:
            self.assertEqual(await pool.fetch("https://trip.com/one"), "https://trip.com/one")
            self.assertEqual(await pool.fetch("https://trip.com/two"), "https://trip.com/two")
            self.assertEqual(await pool.fetch("https://booking.com/one"), "https://booking.com/one")
            self.assertEqual(len(created), 2)
            self.assertEqual(created[0].fetches, ["https://trip.com/one", "https://trip.com/two"])
        finally:
            await pool.close()
        self.assertTrue(all(session.closed for session in created))


class ReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_replay_fetches_rendered_parameters_and_projects_json(self) -> None:
        calls: list[tuple[str, dict]] = []

        class FakeResponse:
            status = 200
            headers = {"content-type": "application/json"}

            def __init__(self, url: str) -> None:
                self.url = url

            async def json(self):
                return {"results": [{"price": 310, "flightNo": "QR102"}]}

        class FakeSession:
            async def start(self):
                return None

            async def fetch(self, url: str, **kwargs):
                calls.append((url, kwargs))
                return FakeResponse(url)

            async def close(self):
                return None

        spec = ExtractionSpec(
            name="flight",
            expected_fields={"price": ("price",), "flight_no": ("flightNo",)},
            required_fields=("price", "flight_no"),
            min_records=1,
            score_threshold=20,
        )
        template = build_replay_template(
            "https://www.trip.com/flights?dcity=gva&ddate=2026-09-25",
            "https://api.trip.com/search?dcity=gva&ddate=2026-09-25&locale=en_xx",
            method="GET",
            content_type="application/json",
            dynamic_query_keys=("dcity", "ddate"),
        )
        assert template is not None
        pool = PersistentSessionPool(session_factory=lambda **_kwargs: FakeSession())
        extractor = UniversalExtractor(session_pool=pool)
        try:
            result = await extractor.replay_one(
                "https://www.trip.com/flights?dcity=par&ddate=2026-12-01",
                spec,
                template,
            )
        finally:
            await extractor.close()

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["flight_no"], "QR102")
        self.assertIn("dcity=par", calls[0][0])
        self.assertIn("ddate=2026-12-01", calls[0][0])
        self.assertIn("locale=en_xx", calls[0][0])


if __name__ == "__main__":
    unittest.main()

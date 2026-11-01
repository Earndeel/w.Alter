from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from universal_extractor import (
    ExtractionResult,
    ExtractionSpec,
    ResponseCandidate,
    StealthyFetcher,
    UniversalExtractor,
    aggregate_records,
    meets_spec,
    project_records,
    score_payload,
)
from universal_router import CamoufoxMaxClient, UniversalRouter
from profile_index import ProfileIndex
from webtop_client import WebtopCdpClient

ROOT = Path(__file__).resolve().parent
PANEL_FILE = ROOT / "panel.html"
HOST = "127.0.0.1"
PORT = 8766
MAX_BODY_BYTES = 1_500_000
RUNS: dict[str, dict[str, Any]] = {}
RUNS_LOCK = threading.RLock()
PROFILE_INDEX = ProfileIndex()


SCENARIO_DEFS: list[dict[str, Any]] = [
    {
        "id": "flight-search",
        "label": "Flight search",
        "group": "travel",
        "icon": "✈",
        "accent": "cyan",
        "description": "Compare fares, journey duration and carrier identity across flight results.",
        "mode": "live",
        "live_supported": True,
        "default_url": (
            "https://www.trip.com/flights/showfarefirst?dcity=gva&acity=bkk"
            "&ddate=2026-09-25&rdate=2026-09-28&triptype=ow&class=y"
            "&lowpricesource=searchform&quantity=1&searchboxarg=t"
            "&nonstoponly=off&sort=price&locale=en_xx&curr=EUR"
        ),
        "expected_fields": {
            "price": ["accurateTotalPrice", "totalPrice", "farePrice", "averagePrice", "price"],
            "duration": ["duration", "transferDuration"],
            "flight_no": ["carrierFlightNo", "flightNo"],
            "airline": ["airlineInfo", "carrierAirlineInfo", "airline"],
            "airport_code": ["airportCode"],
            "currency": ["currency"],
        },
        "required_fields": ["price", "duration", "flight_no"],
        "min_records": 1,
        "score_threshold": 35,
        "replay_query_keys": ["dcity", "acity", "ddate", "rdate", "triptype", "class", "sort", "locale", "curr"],
        "fixture": {
            "journeyList": [
                {
                    "journeyKey": "QR102-GVA-BKK",
                    "duration": "14h 15m",
                    "accurateTotalPrice": 310,
                    "currency": "EUR",
                    "transportList": [
                        {
                            "flight": {
                                "flightNo": "QR102",
                                "airlineInfo": "Qatar Airways",
                                "airportCode": "GVA",
                            }
                        }
                    ],
                },
                {
                    "journeyKey": "TK191-GVA-BKK",
                    "duration": "15h 40m",
                    "accurateTotalPrice": 327,
                    "currency": "EUR",
                    "transportList": [
                        {
                            "flight": {
                                "flightNo": "TK191",
                                "airlineInfo": "Turkish Airlines",
                                "airportCode": "GVA",
                            }
                        }
                    ],
                },
            ]
        },
    },
    {
        "id": "hotel-availability",
        "label": "Hotel availability",
        "group": "travel",
        "icon": "⌂",
        "accent": "violet",
        "description": "Normalize rooms, nightly price, rating and availability from accommodation cards.",
        "mode": "live",
        "live_supported": True,
        "default_url": "https://www.trip.com/hotels/list?city=359&searchWord=Bangkok",
        "expected_fields": {
            "hotel_name": ["hotelName", "hotelTitle", "hotel_name", "name"],
            "price": ["totalPrice", "priceWithTaxes", "price", "total"],
            "nightly_price": ["nightlyPrice", "salePrice", "roomPrice"],
            "total_price": ["totalPrice", "priceWithTaxes", "total"],
            "price_basis": ["priceBasis", "pricingBasis"],
            "room_type": ["roomType", "roomName", "accommodationType", "saleRoomName", "physicsName"],
            "hotel_id": ["hotelId", "hotel_id", "propertyId"],
            "hotel_url": ["hotelUrl", "hotelURL", "url"],
            "rating": ["reviewRating", "rating", "score", "commentScore"],
            "location": ["location", "city", "address", "cityName", "cityNameEn", "positionDesc"],
            "availability": ["available", "availability", "isAvailable"],
            "status": ["status", "availabilityStatus"],
            "rooms_left": ["roomsLeft", "roomQuantity", "roomCount"],
            "currency": ["currency", "currencyCode"],
        },
        "required_fields": ["hotel_name", "price", "room_type", "availability"],
        "min_records": 1,
        "score_threshold": 35,
        "dom_profile": "trip-hotel-list",
        "replay_query_keys": ["city", "searchWord", "checkIn", "checkOut", "adult", "children", "curr"],
        "fixture": {
            "hotelResults": [
                {
                    "hotelName": "Siam Riverside House",
                    "roomType": "Deluxe King",
                    "nightlyPrice": 84,
                    "totalPrice": 99,
                    "available": True,
                    "currencyCode": "EUR",
                    "reviewRating": 4.7,
                    "city": "Bangkok",
                    "roomsLeft": 3,
                },
                {
                    "hotelName": "Ari Garden Suites",
                    "roomType": "Studio Suite",
                    "nightlyPrice": 96,
                    "totalPrice": 112,
                    "available": True,
                    "currencyCode": "EUR",
                    "reviewRating": 4.5,
                    "city": "Bangkok",
                    "roomsLeft": 1,
                },
            ]
        },
    },
    {
        "id": "hotel-detail",
        "label": "Hotel detail",
        "group": "travel",
        "icon": "▣",
        "accent": "violet",
        "description": "Normalize a Trip.com hotel page into one record per room with price basis and availability.",
        "mode": "live",
        "live_supported": True,
        "default_url": "https://www.trip.com/hotels/detail/?cityId=44298&hotelId=2930176",
        "expected_fields": {
            "hotel_name": ["hotelName", "hotelTitle", "hotel_name", "name"],
            "price": ["totalPrice", "priceWithTaxes", "price", "total"],
            "nightly_price": ["nightlyPrice", "salePrice", "roomPrice"],
            "total_price": ["totalPrice", "priceWithTaxes", "total"],
            "price_basis": ["priceBasis", "pricingBasis"],
            "room_type": ["roomType", "roomName", "accommodationType", "saleRoomName", "physicsName"],
            "hotel_id": ["hotelId", "hotel_id", "propertyId"],
            "hotel_url": ["hotelUrl", "hotelURL", "url"],
            "rating": ["reviewRating", "rating", "score", "commentScore"],
            "location": ["location", "city", "address", "cityName", "cityNameEn", "positionDesc"],
            "availability": ["available", "availability", "isAvailable"],
            "status": ["status", "availabilityStatus"],
            "rooms_left": ["roomsLeft", "roomQuantity", "roomCount"],
            "currency": ["currency", "currencyCode"],
        },
        "required_fields": ["hotel_name", "price", "room_type", "availability"],
        "min_records": 1,
        "score_threshold": 35,
        "dom_profile": "trip-hotel-detail",
        "replay_query_keys": ["cityId", "hotelId", "checkIn", "checkOut", "adult", "children", "curr"],
        "fixture": {
            "rooms": [
                {
                    "hotelName": "Siam Riverside House",
                    "hotelId": "fixture-105",
                    "hotelUrl": "https://www.trip.com/hotels/detail/?hotelId=fixture-105",
                    "roomName": "Deluxe King",
                    "nightlyPrice": 84,
                    "totalPrice": 99,
                    "priceBasis": "total",
                    "available": True,
                    "currencyCode": "EUR",
                    "reviewRating": 4.7,
                    "address": "Charoen Nakhon, Bangkok",
                    "roomsLeft": 3,
                },
                {
                    "hotelName": "Siam Riverside House",
                    "hotelId": "fixture-105",
                    "hotelUrl": "https://www.trip.com/hotels/detail/?hotelId=fixture-105",
                    "roomName": "River View Suite",
                    "nightlyPrice": 126,
                    "totalPrice": 148,
                    "priceBasis": "total",
                    "available": False,
                    "currencyCode": "EUR",
                    "reviewRating": 4.7,
                    "address": "Charoen Nakhon, Bangkok",
                    "roomsLeft": 0,
                },
            ]
        },
    },
    {
        "id": "product-monitor",
        "label": "Product monitor",
        "group": "commerce",
        "icon": "◆",
        "accent": "amber",
        "description": "Track price, stock, rating and product identity for a commerce catalog.",
        "mode": "live",
        "live_supported": True,
        "default_url": "https://www.ikea.com/fr/fr/search/?q=lampe",
        "expected_fields": {
            "title": ["productTitle", "productName", "title", "name"],
            "price": ["currentPrice", "salePrice", "price"],
            "stock": ["stockStatus", "availability", "inStock"],
            "rating": ["reviewRating", "rating"],
            "currency": ["currency", "currencyCode"],
        },
        "required_fields": ["title", "price"],
        "min_records": 1,
        "score_threshold": 35,
        "fixture": {
            "items": [
                {
                    "productTitle": "LumaBeam Mini Projector",
                    "currentPrice": 129.9,
                    "currency": "EUR",
                    "stockStatus": "in_stock",
                    "reviewRating": 4.4,
                },
                {
                    "productTitle": "LumaBeam Mini Projector — bundle",
                    "currentPrice": 159.9,
                    "currency": "EUR",
                    "stockStatus": "low_stock",
                    "reviewRating": 4.6,
                },
            ]
        },
    },
    {
        "id": "social-monitoring",
        "label": "Social monitoring",
        "group": "social",
        "icon": "◎",
        "accent": "pink",
        "description": "Collect posts, authors, publication time and engagement without DOM selectors.",
        "mode": "live",
        "live_supported": True,
        "default_url": "https://mastodon.social/api/v1/timelines/tag/travel?limit=20",
        "expected_fields": {
            "author": ["authorName", "username", "acct", "author", "handle", "display_name"],
            "text": ["content", "text", "body", "message"],
            "published_at": ["publishedAt", "createdAt", "created_at", "timestamp"],
            "engagement": ["engagement", "likes", "favourites_count", "replies_count", "reblogs_count", "reactions", "replies"],
            "platform": ["platform", "network", "source"],
        },
        "required_fields": ["author", "text", "published_at"],
        "min_records": 1,
        "score_threshold": 35,
        "fixture": {
            "posts": [
                {
                    "authorName": "@farewatcher",
                    "content": "GVA → BKK under 320 EUR this September.",
                    "publishedAt": "2026-08-04T08:42:00Z",
                    "likes": 182,
                    "platform": "X",
                },
                {
                    "authorName": "@carryonclub",
                    "content": "Turkish is showing a strong one-stop fare today.",
                    "publishedAt": "2026-08-04T09:11:00Z",
                    "likes": 94,
                    "platform": "X",
                },
            ]
        },
    },
    {
        "id": "article-discovery",
        "label": "Article discovery",
        "group": "content",
        "icon": "▤",
        "accent": "green",
        "description": "Extract titles, authors, timestamps and source links from editorial feeds.",
        "mode": "live",
        "live_supported": True,
        "default_url": "https://hn.algolia.com/?query=travel",
        "expected_fields": {
            "title": ["headline", "articleTitle", "title", "story_title"],
            "author": ["byline", "author", "authorName"],
            "published_at": ["publishedAt", "published", "date", "created_at", "createdAt", "created_at_i"],
            "url": ["articleUrl", "canonicalUrl", "url", "link", "story_url"],
            "summary": ["summary", "description", "excerpt"],
            "category": ["category", "section", "topic"],
        },
        "required_fields": ["title", "url", "published_at"],
        "min_records": 1,
        "score_threshold": 35,
        "fixture": {
            "articles": [
                {
                    "headline": "Why regional hubs are reshaping long-haul fares",
                    "byline": "Maya Chen",
                    "publishedAt": "2026-08-04",
                    "articleUrl": "https://example.test/news/regional-hubs",
                    "summary": "A data-led look at connection strategies.",
                    "section": "Aviation",
                },
                {
                    "headline": "The quiet return of shoulder-season travel",
                    "byline": "Noah Martin",
                    "publishedAt": "2026-08-03",
                    "articleUrl": "https://example.test/news/shoulder-season",
                    "summary": "Why flexible dates are becoming valuable again.",
                    "section": "Travel",
                },
            ]
        },
    },
    {
        "id": "lead-directory",
        "label": "Lead directory",
        "group": "content",
        "icon": "⌁",
        "accent": "blue",
        "description": "Turn heterogeneous directory records into a compact lead table.",
        "mode": "live",
        "live_supported": True,
        "default_url": "https://nominatim.openstreetmap.org/search?format=jsonv2&q=hotel%20Bangkok&limit=10",
        "expected_fields": {
            "name": ["businessName", "companyName", "name", "title", "display_name"],
            "location": ["address", "location", "city", "display_name", "lat", "lon"],
            "phone": ["phone", "phoneNumber", "telephone"],
            "category": ["category", "type", "industry"],
            "rating": ["rating", "reviewRating", "score"],
        },
        "required_fields": ["name", "location"],
        "min_records": 1,
        "score_threshold": 30,
        "fixture": {
            "directory": [
                {
                    "businessName": "Riverside Stay Co.",
                    "address": "Charoen Krung, Bangkok",
                    "phoneNumber": "+66 2 555 0182",
                    "category": "Boutique hotel",
                    "rating": 4.8,
                },
                {
                    "businessName": "Ari Mobility Desk",
                    "address": "Ari, Bangkok",
                    "phoneNumber": "+66 2 555 0197",
                    "category": "Travel agency",
                    "rating": 4.3,
                },
            ]
        },
    },
    {
        "id": "noise-rejection",
        "label": "Noise rejection",
        "group": "quality",
        "icon": "⊘",
        "accent": "red",
        "description": "Confirm that analytics and calendar payloads do not masquerade as useful records.",
        "mode": "fixture",
        "live_supported": False,
        "default_url": "fixture://quality/noise-rejection",
        "expected_fields": {
            "price": ["accurateTotalPrice", "totalPrice", "price"],
            "duration": ["duration"],
            "flight_no": ["flightNo", "carrierFlightNo"],
        },
        "required_fields": ["price", "duration", "flight_no"],
        "min_records": 1,
        "score_threshold": 35,
        "fixture": {
            "analytics": {"event": "page_view", "sessionId": "opaque"},
            "calendar": [{"price": 310}, {"price": 315}, {"price": 327}],
            "recommendations": [{"title": "Bangkok hotels", "score": 0.91}],
        },
    },
]

SCENARIOS = {item["id"]: item for item in SCENARIO_DEFS}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def spec_for(scenario: dict[str, Any]) -> ExtractionSpec:
    return ExtractionSpec(
        name=scenario["id"],
        expected_fields={
            key: tuple(values) for key, values in scenario["expected_fields"].items()
        },
        required_fields=tuple(scenario["required_fields"]),
        min_records=scenario["min_records"],
        score_threshold=scenario["score_threshold"],
        dom_profile=scenario.get("dom_profile"),
        replay_query_keys=tuple(scenario.get("replay_query_keys", ())),
    )


def scenario_public_view(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        key: scenario.get(key)
        for key in (
            "id",
            "label",
            "group",
            "icon",
            "accent",
            "description",
            "mode",
            "live_supported",
            "default_url",
            "expected_fields",
            "required_fields",
            "min_records",
            "score_threshold",
            "dom_profile",
            "replay_query_keys",
        )
    }


def json_bytes(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())


def payload_preview(payload: Any, max_chars: int = 120_000) -> Any:
    """Keep the panel useful without returning an unbounded response body."""
    encoded = json.dumps(payload, ensure_ascii=False, default=str)
    if len(encoded) <= max_chars:
        return payload
    return {
        "_truncated": True,
        "_original_chars": len(encoded),
        "_preview": encoded[:max_chars],
    }


def fixture_result(scenario: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    spec = spec_for(scenario)
    payload = scenario["fixture"]
    score, matched_fields, record_count = score_payload(payload, spec)
    candidate = ResponseCandidate(
        url=f"fixture://{scenario['id']}/payload",
        method="FIXTURE",
        status=200,
        content_type="application/json",
        response_bytes=json_bytes(payload),
        elapsed_ms=(time.perf_counter() - started) * 1000,
        payload=payload,
        matched_fields=matched_fields,
        record_count=record_count,
        score=score,
    )
    valid = meets_spec(matched_fields, record_count, spec)
    result = ExtractionResult(
        url=scenario["default_url"],
        elapsed_s=time.perf_counter() - started,
        candidates=[candidate],
        best_candidate=candidate,
        records=aggregate_records([candidate], spec),
        valid_candidate_count=int(valid),
    )
    summary = result.summary()
    summary.update(
        {
            "scenario_id": scenario["id"],
            "scenario_label": scenario["label"],
            "mode": "fixture",
            "source": "synthetic fixture",
            "required_fields": scenario["required_fields"],
            "threshold": scenario["score_threshold"],
            "fixture_valid": valid,
            "payload_preview": payload_preview(payload),
        }
    )
    return summary


async def live_result(url: str, scenario: dict[str, Any]) -> dict[str, Any]:
    extractor = None
    if StealthyFetcher is not None:
        extractor = UniversalExtractor(
            concurrency=1,
            candidate_wait_ms=30_000,
            return_wait_ms=250,
            persistent_sessions=True,
            session_max_pages=2,
        )
    router = UniversalRouter(
        scrapling_extractor=extractor,
        camoufox_client=CamoufoxMaxClient(),
        webtop_client=WebtopCdpClient(),
        profile_index=PROFILE_INDEX,
    )
    try:
        routed = await router.extract_one(url, spec_for(scenario), mode="auto")
    finally:
        await router.close()
    summary = routed.summary()
    summary.update(
        {
            "scenario_id": scenario["id"],
            "scenario_label": scenario["label"],
            "mode": "live",
            "source": f"universal router ({routed.route})",
            "required_fields": scenario["required_fields"],
            "threshold": scenario["score_threshold"],
            "fixture_valid": None,
            "payload_preview": payload_preview(
                routed.result.best_candidate.payload if routed.result.best_candidate else {}
            ),
        }
    )
    return summary


def append_event(run_id: str, message: str, level: str = "info") -> None:
    with RUNS_LOCK:
        run = RUNS.get(run_id)
        if run is not None:
            run.setdefault("events", []).append(
                {"at": utc_now(), "message": message, "level": level}
            )


def worker(run_id: str, scenario_id: str, mode: str, url: str) -> None:
    scenario = SCENARIOS[scenario_id]
    with RUNS_LOCK:
        RUNS[run_id].update({"state": "running", "started_at": utc_now()})
    append_event(run_id, f"Loading {scenario['label']} / mode={mode}")
    try:
        if mode == "fixture":
            append_event(run_id, "Scoring synthetic JSON payload")
            summary = fixture_result(scenario)
        else:
            append_event(run_id, "Opening persistent stealth session")
            append_event(run_id, "Capturing XHR / fetch JSON responses")
            summary = asyncio.run(live_result(url, scenario))
        append_event(
            run_id,
            f"Candidate score={summary['best_candidate']['score'] if summary['best_candidate'] else 0} "
            f"records={summary['record_count']}",
            "success" if summary["valid_candidate_count"] else "warning",
        )
        with RUNS_LOCK:
            RUNS[run_id].update(
                {
                    "state": "complete",
                    "finished_at": utc_now(),
                    "result": summary,
                }
            )
    except Exception as exc:  # the panel should expose failures, not vanish
        message = f"{type(exc).__name__}: {exc}"[:500]
        append_event(run_id, message, "error")
        with RUNS_LOCK:
            RUNS[run_id].update(
                {
                    "state": "error",
                    "finished_at": utc_now(),
                    "error": message,
                }
            )


def public_run(run: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(run, ensure_ascii=False, default=str))


def is_public_url(raw_url: str) -> tuple[bool, str]:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False, "L'URL live doit utiliser http(s) et posséder un hôte"
    hostname = parsed.hostname.strip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"}:
        return False, "Les hôtes locaux sont bloqués par le panneau"
    try:
        literal = ipaddress.ip_address(hostname)
        if literal.is_private or literal.is_loopback or literal.is_link_local or literal.is_reserved:
            return False, "Les adresses réseau privées sont bloquées par le panneau"
        return True, ""
    except ValueError:
        pass
    try:
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        return False, f"Résolution DNS impossible: {exc}"
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, "L'hôte résout vers un réseau privé, requête bloquée"
    return True, ""


class PanelHandler(BaseHTTPRequestHandler):
    server_version = "UniversalExtractorPanel/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the terminal readable; the panel itself carries the useful trace.
        return

    def send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/panel.html"}:
            try:
                data = PANEL_FILE.read_bytes()
            except FileNotFoundError:
                self.send_error(404, "panel.html missing")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if parsed.path == "/api/health":
            with RUNS_LOCK:
                active = sum(run["state"] in {"queued", "running"} for run in RUNS.values())
            self.send_json(
                {
                    "ok": True,
                    "engine": "universal-json-first-extractor",
                    "scrapling_available": StealthyFetcher is not None,
                    "active_runs": active,
                    "scenario_count": len(SCENARIO_DEFS),
                    "profile_index": PROFILE_INDEX.stats(),
                }
            )
            return
        if parsed.path == "/api/profiles":
            self.send_json({"profiles": PROFILE_INDEX.list_profiles(), "stats": PROFILE_INDEX.stats()})
            return
        if parsed.path == "/api/scenarios":
            self.send_json({"scenarios": [scenario_public_view(item) for item in SCENARIO_DEFS]})
            return
        if parsed.path.startswith("/api/runs/"):
            run_id = parsed.path.rsplit("/", 1)[-1]
            with RUNS_LOCK:
                run = RUNS.get(run_id)
                if run is None:
                    self.send_json({"error": "run not found"}, 404)
                else:
                    self.send_json(public_run(run))
            return
        self.send_error(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/runs":
            self.send_json({"error": "not found"}, 404)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length > MAX_BODY_BYTES:
            self.send_json({"error": "request too large"}, 413)
            return
        try:
            body = json.loads(self.rfile.read(content_length) or b"{}")
        except json.JSONDecodeError:
            self.send_json({"error": "invalid JSON"}, 400)
            return
        scenario_id = body.get("scenario_id")
        mode = body.get("mode", "fixture")
        scenario = SCENARIOS.get(scenario_id)
        if scenario is None:
            self.send_json({"error": "unknown scenario"}, 400)
            return
        if mode not in {"fixture", "live"}:
            self.send_json({"error": "mode must be fixture or live"}, 400)
            return
        if mode == "live" and not scenario["live_supported"]:
            self.send_json({"error": "live mode is not enabled for this scenario yet"}, 400)
            return
        url = str(body.get("url") or scenario["default_url"])
        if mode == "live":
            valid, reason = is_public_url(url)
            if not valid:
                self.send_json({"error": reason}, 400)
                return
        run_id = uuid.uuid4().hex[:12]
        run = {
            "id": run_id,
            "scenario_id": scenario_id,
            "scenario_label": scenario["label"],
            "mode": mode,
            "url": url,
            "state": "queued",
            "created_at": utc_now(),
            "events": [],
        }
        with RUNS_LOCK:
            completed = [
                key for key, value in RUNS.items()
                if value["state"] in {"complete", "error"}
            ]
            for old_id in completed[:-40]:
                RUNS.pop(old_id, None)
            RUNS[run_id] = run
        thread = threading.Thread(
            target=worker,
            args=(run_id, scenario_id, mode, url),
            daemon=True,
            name=f"extractor-run-{run_id}",
        )
        thread.start()
        self.send_json({"run_id": run_id, "state": "queued"}, 202)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), PanelHandler)
    print(f"Universal Extractor Test Lab: http://{HOST}:{PORT}", flush=True)
    print(f"Scenarios: {len(SCENARIO_DEFS)} | Scrapling: {'ready' if StealthyFetcher else 'missing'}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPanel stopped", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

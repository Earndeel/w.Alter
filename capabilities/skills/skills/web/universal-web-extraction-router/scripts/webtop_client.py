from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Mapping
from typing import Any

from universal_extractor import (
    ExtractionResult,
    ExtractionSpec,
    ResponseCandidate,
    finalize_extraction_result,
    meets_spec,
    score_payload,
)


DEFAULT_WEBTOP_CDP_URL = os.environ.get("UNIVERSAL_WEBTOP_CDP_URL", "http://127.0.0.1:9223")
_MAX_CAPTURE_ITEMS = 80
_MAX_CAPTURE_BODY_CHARS = 1_200_000
_MAX_DOM_RECORDS = 50


def _first_value(sources: list[Mapping[str, Any]], keys: tuple[str, ...]) -> Any:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                return value
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace("\u00a0", "")
    match = re.search(r"[-+]?\d[\d,.]*", raw)
    if not match:
        return None
    token = match.group(0)
    if "," in token and "." in token:
        token = token.replace(",", "")
    elif token.count(",") == 1 and len(token.rsplit(",", 1)[1]) <= 2:
        token = token.replace(",", ".")
    else:
        token = token.replace(",", "")
    try:
        return float(token)
    except ValueError:
        return None


def _availability(sources: list[Mapping[str, Any]]) -> bool | None:
    explicit = _first_value(sources, ("available", "availability", "isAvailable"))
    if isinstance(explicit, bool):
        return explicit
    if explicit is not None:
        value = str(explicit).strip().lower()
        if value in {"true", "yes", "available", "in_stock", "instock", "1"}:
            return True
        if value in {"false", "no", "sold_out", "sold out", "unavailable", "0"}:
            return False
    sold_out = _first_value(sources, ("soldOut", "sold_out", "isSoldOut"))
    if isinstance(sold_out, bool):
        return not sold_out
    if sold_out is not None and str(sold_out).strip().lower() in {"true", "yes", "1"}:
        return False
    status = str(_first_value(sources, ("status", "availabilityStatus", "availabilityText")) or "").lower()
    if re.search(r"sold\s*out|unavailable|no\s*rooms?", status):
        return False
    if re.search(r"available|in\s*stock|book\s*now", status):
        return True
    return None


def normalize_trip_hotel_detail_payload(payload: Any) -> dict[str, Any]:
    """Expand a Trip.com detail payload into one normalized record per room."""
    if not isinstance(payload, Mapping):
        return {"hotelResults": []}
    context = payload.get("hotel") if isinstance(payload.get("hotel"), Mapping) else {}
    raw_rooms = payload.get("rooms") or payload.get("roomResults") or payload.get("hotelResults")
    if not isinstance(raw_rooms, list):
        raw_rooms = [payload]
    records: list[dict[str, Any]] = []
    for raw_room in raw_rooms[:_MAX_DOM_RECORDS]:
        room = raw_room if isinstance(raw_room, Mapping) else {}
        sources = [room, context]
        total = _number(_first_value(sources, ("totalPrice", "priceWithTaxes", "total")))
        nightly = _number(_first_value(sources, ("nightlyPrice", "salePrice", "roomPrice")))
        generic_price = _number(_first_value(sources, ("price",)))
        if total is None and nightly is None and generic_price is not None:
            nightly = generic_price
        price = total if total is not None else nightly
        explicit_basis = _first_value(sources, ("priceBasis", "pricingBasis"))
        basis = str(explicit_basis).lower() if explicit_basis else ("total" if total is not None else "nightly")
        available = _availability(sources)
        status = _first_value(sources, ("status", "availabilityStatus"))
        if status in (None, ""):
            status = "available" if available is True else ("sold_out" if available is False else "unknown")
        record = {
            "hotelName": _first_value(sources, ("hotelName", "hotelTitle", "hotel_name", "name")),
            "hotelId": _first_value(sources, ("hotelId", "hotel_id", "propertyId")),
            "hotelUrl": _first_value(sources, ("hotelUrl", "hotelURL", "url")),
            "roomType": _first_value(sources, ("roomType", "roomName", "accommodationType", "saleRoomName", "physicsName")),
            "nightlyPrice": nightly,
            "totalPrice": total,
            "price": price,
            "priceBasis": basis,
            "currency": _first_value(sources, ("currency", "currencyCode")),
            "reviewRating": _number(_first_value(sources, ("reviewRating", "rating", "score", "commentScore"))),
            "location": _first_value(sources, ("location", "city", "address", "cityName", "cityNameEn", "positionDesc")),
            "available": available,
            "status": status,
            "roomsLeft": _number(_first_value(sources, ("roomsLeft", "roomQuantity", "roomCount"))),
        }
        if record["hotelName"] or record["roomType"] or record["price"] is not None:
            records.append(record)
    return {"hotelResults": records}


class WebtopCdpError(RuntimeError):
    """Raised when the persistent Webtop Chromium session is unavailable."""


_TRIP_HOTEL_DOM_EXPRESSION = r"""
() => {
  const text = node => (node?.innerText || '').replace(/\u00a0/g, ' ').trim();
  const firstText = (root, selectors) => {
    for (const selector of selectors) {
      const value = text(root.querySelector(selector));
      if (value) return value;
    }
    return '';
  };
  const firstAttr = (root, selector, attr) => root.querySelector(selector)?.getAttribute(attr) || '';
  const numberFrom = value => {
    const match = String(value || '').replace(/,/g, '').match(/[-+]?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : null;
  };
  const money = value => {
    const raw = text(value);
    const number = numberFrom(raw);
    if (number === null) return { value: null, text: raw, currency: '' };
    const currency = (raw.match(/(?:US|CA|AU)\$|[$€£¥]|\b[A-Z]{3}\b/i) || [''])[0];
    return { value: number, text: raw, currency };
  };
  const rating = value => {
    const raw = text(value);
    const match = raw.match(/\d+(?:\.\d+)?\s*\/\s*10/);
    return match ? Number(match[0].replace(/\/10/, '').trim()) : numberFrom(raw);
  };
  const list = [...document.querySelectorAll('.list-item')].slice(0, 50);
  const hotelResults = list.map(card => {
    const fullText = text(card);
    const totalNode = card.querySelector('.price-highlight, .price-explain');
    const nightlyNode = card.querySelector('.sale');
    const total = money(totalNode);
    const nightly = money(nightlyNode);
    const roomType = firstText(card, ['.room-name', '[class*="room-name"]']);
    const nameNode = card.querySelector('.hotel-title a, .hotelName, [class*="hotel-title"] a');
    const hotelName = text(nameNode);
    const href = nameNode?.getAttribute('href') || card.querySelector('a[href]')?.getAttribute('href') || '';
    const scoreNode = card.querySelector('.comment-score, [class*="comment-score"], [class*="rating"]');
    const locationLine = fullText.split('\n').find(line => /show on map$/i.test(line)) || '';
    const location = locationLine.replace(/\s*show on map\s*$/i, '').trim();
    const roomsLeftMatch = fullText.match(/only\s+(\d+)\s+left/i);
    const soldOut = /sold\s*out|no\s*rooms?/i.test(fullText);
    const available = !soldOut && /check\s+availability/i.test(fullText);
    const hotelCard = card.querySelector('.hotel-card, [data-offline-hotelid]');
    const hotelId = hotelCard?.getAttribute('data-offline-hotelid') || hotelCard?.id || '';
    const pageUrl = new URL(window.location.href);
    const detailUrl = hotelId ? new URL('/hotels/detail/', pageUrl.origin) : null;
    if (detailUrl) {
      const cityId = pageUrl.searchParams.get('city') || '';
      if (cityId) detailUrl.searchParams.set('cityId', cityId);
      detailUrl.searchParams.set('hotelId', hotelId);
      for (const key of ['checkIn', 'checkOut', 'adult', 'children', 'curr']) {
        const value = pageUrl.searchParams.get(key);
        if (value) detailUrl.searchParams.set(key, value);
      }
    }
    const hotelUrl = href ? new URL(href, pageUrl.href).href : (detailUrl ? detailUrl.href : '');
    return {
      hotelName,
      hotelId,
      hotelUrl,
      roomType,
      nightlyPrice: nightly.value,
      totalPrice: total.value,
      price: total.value ?? nightly.value,
      priceBasis: total.value !== null ? 'total' : 'nightly',
      priceText: total.text || nightly.text,
      currency: total.currency || nightly.currency,
      reviewRating: rating(scoreNode),
      location,
      roomsLeft: roomsLeftMatch ? Number(roomsLeftMatch[1]) : null,
      availability: available,
      isSoldOut: soldOut,
      status: available ? 'available' : (soldOut ? 'sold_out' : 'unknown'),
    };
  }).filter(item => item.hotelName || item.roomType || item.price !== null);
  return { hotelResults };
}
"""

_TRIP_HOTEL_DETAIL_DOM_EXPRESSION = r"""
() => {
  const text = node => (node?.innerText || '').replace(/\u00a0/g, ' ').trim();
  const firstText = (root, selectors) => {
    for (const selector of selectors) {
      const value = text(root.querySelector(selector));
      if (value) return value;
    }
    return '';
  };
  const numberFrom = value => {
    const match = String(value || '').replace(/,/g, '').match(/[-+]?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : null;
  };
  const money = node => ({ value: numberFrom(text(node)), text: text(node) });
  const page = new URL(window.location.href);
  const hotelId = page.searchParams.get('hotelId') || '';
  const hotel = {
    hotelName: firstText(document, ['h1', '[data-testid*="hotel-name"]', '[class*="hotel-name"]', '[class*="hotelName"]']),
    hotelId,
    hotelUrl: page.href,
    reviewRating: firstText(document, ['[class*="comment-score"]', '[class*="rating"]', '[data-testid*="rating"]']),
    address: firstText(document, ['[class*="address"]', '[class*="location"]', '[class*="position"]']),
  };
  const selectors = [
    '.room-card', '.room-item', '[data-testid*="room"]',
    '[class*="room-card"]', '[class*="room-item"]', '[class*="roomCard"]'
  ];
  const seen = new Set();
  const roomNodes = selectors.flatMap(selector => [...document.querySelectorAll(selector)])
    .filter(node => { if (seen.has(node)) return false; seen.add(node); return true; })
    .slice(0, 50);
  const rooms = roomNodes.map(card => {
    const body = text(card);
    const roomType = firstText(card, ['h2', 'h3', 'h4', '.room-name', '[class*="room-name"]', '[class*="roomName"]']);
    const totalNode = card.querySelector('[class*="total"], [class*="price-highlight"], [class*="price-explain"]');
    const nightlyNode = card.querySelector('[class*="night"], [class*="sale"], [class*="room-price"]');
    const total = money(totalNode);
    const nightly = money(nightlyNode);
    const soldOut = /sold\s*out|unavailable|no\s*rooms?/i.test(body);
    const available = soldOut ? false : (/book\s*now|reserve|select\s*room|available/i.test(body) ? true : null);
    const roomsLeft = body.match(/(?:only|just)\s+(\d+)\s+(?:rooms?\s+)?left/i);
    return {
      roomName: roomType,
      nightlyPrice: nightly.value,
      totalPrice: total.value,
      price: total.value ?? nightly.value,
      currency: (body.match(/(?:US|CA|AU)\$|[$€£¥]|\b[A-Z]{3}\b/i) || [''])[0],
      available,
      soldOut,
      status: available === true ? 'available' : (available === false ? 'sold_out' : 'unknown'),
      roomsLeft: roomsLeft ? Number(roomsLeft[1]) : null,
    };
  }).filter(room => room.roomName || room.price !== null);
  return { hotel, rooms };
}
"""

_GENERIC_DOM_EXPRESSION = r"""
() => {
  const text = node => (node?.innerText || '').replace(/\u00a0/g, ' ').trim();
  const price = value => {
    const raw = text(value);
    const match = raw.match(/(?:[$€£¥]|(?:US|CA|AU)\$)\s*[\d,.]+|\b\d+[,.]?\d*\s*(?:USD|EUR|GBP)\b/i);
    return match ? match[0] : '';
  };
  const nodes = [...document.querySelectorAll('article, li, [data-testid*="card"], [class*="card"], [class*="item"]')];
  const seen = new Set();
  const items = [];
  for (const node of nodes) {
    const body = text(node);
    if (body.length < 12 || body.length > 4000) continue;
    const link = node.querySelector('a[href]');
    const heading = node.querySelector('h1,h2,h3,h4,[role="heading"]');
    const item = {
      title: text(heading) || text(link),
      name: text(heading) || text(link),
      url: link?.href || '',
      text: body,
      price: price(node),
    };
    const key = JSON.stringify(item);
    if (item.title || item.url || item.price) {
      if (!seen.has(key)) { seen.add(key); items.push(item); }
    }
    if (items.length >= 50) break;
  }
  return { items };
}
"""


def _dom_expression(spec: ExtractionSpec) -> str:
    if spec.dom_profile == "trip-hotel-list":
        return _TRIP_HOTEL_DOM_EXPRESSION
    if spec.dom_profile == "trip-hotel-detail":
        return _TRIP_HOTEL_DETAIL_DOM_EXPRESSION
    return _GENERIC_DOM_EXPRESSION


def _dom_payload_is_settled(payload: Any, spec: ExtractionSpec) -> bool:
    """Avoid stopping a profile probe before its useful links are hydrated."""
    if spec.dom_profile not in {"trip-hotel-list", "trip-hotel-detail"}:
        return True
    records = payload.get("hotelResults") if isinstance(payload, Mapping) else None
    if spec.dom_profile == "trip-hotel-detail" and not isinstance(records, list):
        records = payload.get("rooms") if isinstance(payload, Mapping) else None
    if not isinstance(records, list):
        return False
    if spec.dom_profile == "trip-hotel-detail":
        return any(isinstance(record, Mapping) and (record.get("roomName") or record.get("price")) for record in records)
    return any(
        isinstance(record, Mapping)
        and str(record.get("hotelUrl") or "").startswith(("http://", "https://"))
        for record in records
    )


def _candidate_from_payload(
    *,
    payload: Any,
    url: str,
    method: str,
    status: int,
    content_type: str,
    response_bytes: int,
    elapsed_ms: float,
    spec: ExtractionSpec,
    request_body_bytes: int = 0,
) -> ResponseCandidate:
    score, matched_fields, record_count = score_payload(payload, spec)
    return ResponseCandidate(
        url=url,
        method=method,
        status=status,
        content_type=content_type,
        response_bytes=response_bytes,
        elapsed_ms=elapsed_ms,
        payload=payload,
        matched_fields=matched_fields,
        record_count=record_count,
        score=score,
        request_body_bytes=request_body_bytes,
    )


class WebtopCdpClient:
    """Use the persistent Webtop Chromium session as the final extractor."""

    def __init__(
        self,
        *,
        cdp_url: str = DEFAULT_WEBTOP_CDP_URL,
        navigation_timeout_seconds: float = 35.0,
        wait_seconds: float = 12.0,
    ) -> None:
        self.cdp_url = cdp_url.rstrip("/")
        self.navigation_timeout_seconds = max(5.0, navigation_timeout_seconds)
        self.wait_seconds = max(0.5, wait_seconds)

    def _cdp_urls(self) -> tuple[str, ...]:
        """Try the container-forwarded port and the host-local port once each."""
        urls = [self.cdp_url]
        if self.cdp_url in {"http://127.0.0.1:9223", "http://localhost:9223"}:
            urls.append(self.cdp_url.rsplit(":", 1)[0] + ":9222")
        elif self.cdp_url in {"http://127.0.0.1:9222", "http://localhost:9222"}:
            urls.append(self.cdp_url.rsplit(":", 1)[0] + ":9223")
        return tuple(dict.fromkeys(urls))

    async def extract_one(self, url: str, spec: ExtractionSpec) -> ExtractionResult:
        started = time.perf_counter()
        candidates: list[ResponseCandidate] = []
        seen: set[str] = set()
        capture_tasks: set[asyncio.Task[Any]] = set()
        html_bytes = 0
        error: str | None = None
        page = None
        playwright = None

        def add_candidate(candidate: ResponseCandidate) -> None:
            key = f"{candidate.method}|{candidate.url}|{json.dumps(candidate.payload, ensure_ascii=False, sort_keys=True, default=str)}"
            if key in seen:
                return
            seen.add(key)
            candidates.append(candidate)

        async def capture_response(response: Any) -> None:
            try:
                request = response.request
                if request.resource_type not in {"xhr", "fetch", "document"}:
                    return
                headers = response.headers
                content_type = str(headers.get("content-type", ""))
                body = await response.body()
                if not body or len(body) > _MAX_CAPTURE_BODY_CHARS:
                    return
                text = body.decode("utf-8", errors="replace")
                if "json" not in content_type.lower() and not re.match(r"^\s*[\[{]", text):
                    return
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    return
                request_body = request.post_data or ""
                add_candidate(
                    _candidate_from_payload(
                        payload=payload,
                        url=response.url,
                        method=request.method,
                        status=response.status,
                        content_type=content_type or "application/json",
                        response_bytes=len(body),
                        elapsed_ms=(time.perf_counter() - started) * 1000,
                        spec=spec,
                        request_body_bytes=len(request_body.encode()),
                    )
                )
            except Exception:
                # A response can disappear while a SPA navigates. It must not
                # turn a usable DOM result into a browser-wide failure.
                return

        def on_response(response: Any) -> None:
            task = asyncio.create_task(capture_response(response))
            capture_tasks.add(task)
            task.add_done_callback(capture_tasks.discard)

        try:
            try:
                from playwright.async_api import TimeoutError as PlaywrightTimeoutError
                from playwright.async_api import async_playwright
            except ImportError as exc:  # pragma: no cover - environment-specific
                raise WebtopCdpError("Playwright is required for the Webtop CDP fallback") from exc

            playwright = await async_playwright().start()
            browser = None
            connect_error: Exception | None = None
            for cdp_url in self._cdp_urls():
                try:
                    browser = await playwright.chromium.connect_over_cdp(cdp_url, timeout=5000)
                    break
                except Exception as exc:
                    connect_error = exc
            if browser is None:
                raise WebtopCdpError(
                    f"Webtop CDP unavailable at {', '.join(self._cdp_urls())}: {connect_error}"
                )
            if not browser.contexts:
                raise WebtopCdpError("Webtop CDP exposed no browser context")
            context = browser.contexts[0]
            page = await context.new_page()

            async def capture_dom_candidate() -> ResponseCandidate | None:
                if page is None:
                    return None
                dom_payload = await page.evaluate(_dom_expression(spec))
                if spec.dom_profile == "trip-hotel-detail":
                    dom_payload = normalize_trip_hotel_detail_payload(dom_payload)
                if not isinstance(dom_payload, Mapping):
                    return None
                encoded = json.dumps(dom_payload, ensure_ascii=False, default=str)
                candidate = _candidate_from_payload(
                    payload=dom_payload,
                    url=page.url or url,
                    method="DOM",
                    status=200,
                    content_type="text/html",
                    response_bytes=len(encoded.encode()),
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                    spec=spec,
                )
                add_candidate(candidate)
                return candidate

            page.on("response", on_response)
            page.set_default_navigation_timeout(int(self.navigation_timeout_seconds * 1000))
            try:
                await page.goto(url, wait_until="domcontentloaded")
            except PlaywrightTimeoutError as exc:
                error = f"NavigationTimeout: {exc}"[:500]

            deadline = time.monotonic() + self.wait_seconds
            next_dom_probe = time.monotonic()
            while time.monotonic() < deadline:
                await asyncio.sleep(0.25)
                if spec.dom_profile and time.monotonic() >= next_dom_probe:
                    try:
                        dom_candidate = await capture_dom_candidate()
                        if dom_candidate and _dom_payload_is_settled(dom_candidate.payload, spec):
                            if meets_spec(dom_candidate.matched_fields, dom_candidate.record_count, spec):
                                break
                    except Exception:
                        pass
                    next_dom_probe = time.monotonic() + 0.75
                if any(
                    meets_spec(candidate.matched_fields, candidate.record_count, spec)
                    for candidate in candidates
                ):
                    break
            if capture_tasks:
                await asyncio.gather(*capture_tasks, return_exceptions=True)

            if not any(
                meets_spec(candidate.matched_fields, candidate.record_count, spec)
                for candidate in candidates
            ):
                try:
                    await capture_dom_candidate()
                except Exception:
                    pass
            try:
                html_bytes = int(await page.evaluate("document.documentElement?.outerHTML?.length || 0"))
            except Exception:
                html_bytes = 0
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:500]
        finally:
            if capture_tasks:
                await asyncio.gather(*capture_tasks, return_exceptions=True)
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass
            if playwright is not None:
                try:
                    await playwright.stop()
                except Exception:
                    pass

        return finalize_extraction_result(
            url,
            spec,
            started,
            candidates[:_MAX_CAPTURE_ITEMS],
            html_bytes=html_bytes,
            error=error,
        )

    async def close(self) -> None:
        """The CDP browser remains owned by Webtop; this client owns no process."""
        return None

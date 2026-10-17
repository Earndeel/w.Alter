"""Static HTML extraction (fast path for simple pages).

The JSON-first pipeline ignores `text/html` responses, which made plain static
catalog pages escalate to a browser needlessly. This module extracts records
from the HTML body the probe already fetched, using only structural signals:
repeated container blocks + alias matching on element attributes/text.

No LLM. No network. Deterministic. If it cannot satisfy the contract it says
so and the router escalates normally.
"""
from __future__ import annotations

import re
import time
from typing import Any

from bs4 import BeautifulSoup, Tag

from universal_extractor import (
    ExtractionResult,
    ExtractionSpec,
    ResponseCandidate,
    finalize_extraction_result,
    normalize_token,
)

_CURRENCY_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:£|€|\$|¥|฿|₹|₩|R\$|US\$|[A-Z]{3})\s*[\d][\d.,]*(?![A-Za-z])",
    re.IGNORECASE,
)
# Container candidates for repeated product-like blocks.
_CONTAINER_TAGS = ("article", "li", "tr", "div", "section", "ul")
_CONTAINER_HINTS = ("product", "item", "card", "result", "offer", "listing", "book", "hotel", "room")


def _alias_tokens(aliases: tuple[str, ...]) -> set[str]:
    tokens: set[str] = set()
    for alias in aliases:
        token = normalize_token(alias)
        if token and len(token) >= 3:
            tokens.add(token)
    return tokens


def _container_score(tag: Tag) -> float:
    """Score how likely an element is a repeated record container."""
    class_ = " ".join(tag.get("class", [])) if tag else ""
    id_ = str(tag.get("id", "")) if tag else ""
    haystack = f"{tag.name} {class_} {id_}".lower()
    hints = sum(1 for hint in _CONTAINER_HINTS if hint in haystack)
    # Direct children anchor/price signals make it a much better container.
    return float(hints) + (1.5 if tag.find("a", recursive=False) is not None else 0.0)


def _text_of(node: Tag) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


def _field_value(container: Tag, aliases: tuple[str, ...], *, is_price: bool) -> str | None:
    """Find a field value inside a container using alias-based heuristics."""
    tokens = _alias_tokens(aliases)
    if is_price:
        # Price must be an actual currency value; never fall back to a title.
        texts = [t for t in container.stripped_strings if _CURRENCY_RE.search(t)]
        return texts[0] if texts else None
    # Preferred signals, in order: title/alt attributes, heading text,
    # text of elements whose class/id/name matches an alias token.
    for node in container.find_all(["a", "img"], recursive=True)[:12]:
        attr = str(node.get("title") or node.get("alt") or "")
        if attr and len(attr) > 2:
            return attr
    for node in container.find_all(["h1", "h2", "h3", "h4"]):
        text = _text_of(node)
        if text:
            return text
    for node in container.find_all(True):
        if node.name in ("script", "style", "a", "img"):
            continue
        class_ = " ".join(node.get("class", [])) if node else ""
        id_ = str(node.get("id", "")) if node else ""
        haystack = f"{node.name} {class_} {id_}".lower()
        if any(alias in haystack for alias in tokens):
            text = _text_of(node)
            if text:
                return text
    return None


def extract_static_html(
    url: str,
    html: str,
    spec: ExtractionSpec,
    *,
    max_containers: int = 100,
) -> ExtractionResult:
    """Extract repeated records from a static HTML body using the spec's aliases.

    Returns an ExtractionResult identical in shape to the other backends, so
    the router validates it with the exact same contract.
    """
    started = time.perf_counter()
    if not html or not html.strip():
        return finalize_extraction_result(
            url, spec, started, [], error="Static HTML backend received an empty body"
        )
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:  # pragma: no cover - defensive
        return finalize_extraction_result(
            url, spec, started, [], error=f"Static HTML parse failed: {exc}"[:300]
        )

    records: list[dict[str, Any]] = []
    required = set(spec.required_fields)
    price_canonical = next(
        (key for key in spec.expected_fields if "price" in normalize_token(key)), None
    )
    title_canonical = next(
        (key for key in spec.expected_fields if any(t in normalize_token(key) for t in ("title", "name"))), None
    )

    def find_title(container: Tag) -> str | None:
        for node in container.find_all(["a", "img"], recursive=True):
            attr = str(node.get("title") or node.get("alt") or "")
            if attr and len(attr) > 2:
                return attr
        for node in container.find_all(["h1", "h2", "h3", "h4"]):
            text = _text_of(node)
            if text:
                return text
        return None

    price_nodes: list[Tag] = []
    for node in soup.find_all(True):
        if _CURRENCY_RE.search(_text_of(node)) and len(_text_of(node)) < 80:
            price_nodes.append(node)
    # De-duplicate price signals inside the same subtree (price_color p + parent div).
    unique_price_containers: list[Tag] = []
    for node in price_nodes:
        if any(node in parent.find_all(True) for parent in unique_price_containers):
            continue
        unique_price_containers.append(node)

    chosen: list[Tag] = []
    for price_node in unique_price_containers[: max_containers * 3]:
        # Innermost ancestor that holds both this price and a title: start by
        # checking price_node itself (a product li often carries both), then
        # climb until an ancestor has a title.
        block: Tag | None = None
        candidate = price_node
        while candidate is not None:
            if find_title(candidate) is not None:
                block = candidate
                break
            candidate = candidate.parent
        if block is None:
            continue
        # Keep only one block per product subtree.
        if any(block in prior.find_all(True) or prior in block.find_all(True) for prior in chosen):
            continue
        chosen.append(block)
        if len(chosen) >= max_containers:
            break

    for tag in chosen:
        record: dict[str, Any] = {}
        for canonical, aliases in spec.expected_fields.items():
            is_price = "price" in normalize_token(canonical)
            if is_price:
                values = [
                    t for t in tag.stripped_strings if _CURRENCY_RE.search(t) and len(t) < 80
                ]
                value = values[0] if values else None
            elif canonical == title_canonical:
                value = find_title(tag)
            else:
                value = _field_value(tag, tuple(aliases), is_price=False)
            if value is not None:
                record[canonical] = value
        if required.issubset(record.keys()):
            records.append(record)
            if len(records) >= max_containers:
                break

    if not records:
        return finalize_extraction_result(
            url,
            spec,
            started,
            [],
            error=f"Static HTML: no container satisfied required fields {sorted(required)}",
        )

    # One candidate per first record; scoring mirrors the JSON backends.
    score, matched_fields, record_count = _score_records(records, spec)
    candidate = ResponseCandidate(
        url=url,
        method="DOM",
        status=200,
        content_type="text/html",
        response_bytes=len(html.encode("utf-8", errors="replace")),
        elapsed_ms=(time.perf_counter() - started) * 1000,
        payload={"records": records},
        matched_fields=matched_fields,
        record_count=record_count,
        score=score,
    )
    return finalize_extraction_result(url, spec, started, [candidate])


def _score_records(records: list[dict[str, Any]], spec: ExtractionSpec):
    """Best-effort scoring: how many required fields are present per record."""
    required = set(spec.required_fields)
    matched = tuple(sorted(required)) if all(r and required.issubset(r.keys()) for r in records[:2]) else ()
    record_count = len(records)
    # Score: 60 base for contract shape + 40 scaled by completeness.
    score = 60.0 + 40.0 * min(1.0, record_count / max(1, spec.min_records))
    return score, matched, record_count
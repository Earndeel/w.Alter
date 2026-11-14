#!/usr/bin/env python3
"""Refresh live AA Intelligence Pareto data and optional Kie.ai pricing evidence.

The collector is deterministic and does not call an LLM. It stores an
Intelligence-only snapshot under ``$HERMES_HOME/cache/aa-pareto`` or the path
passed with ``--output-dir``. Multimodal AA leaderboards are collected by the
separate ``refresh_modalities.py`` module.

Dependencies: playwright and requests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

AA_MODEL_URL = "https://artificialanalysis.ai/models/{}"
KIE_URL = "https://kie.ai/{}"
KIE_API_URL = "https://api.kie.ai/client/v1/model-pricing/page"
DEFAULT_ANCHORS = ("gpt-5-6-luna", "gpt-5-5", "deepseek-v4-pro")
RSC_PUSH_PATTERN = re.compile(
    r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)'
)
KIE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def hermes_home() -> Path:
    """Resolve the active profile home without hard-coding it in normal use."""
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        return Path(get_hermes_home())
    except Exception:
        configured = os.environ.get("HERMES_HOME")
        if configured:
            return Path(configured).expanduser()
        return Path.home() / ".hermes"


def default_output_dir() -> Path:
    return hermes_home() / "cache" / "aa-pareto"


def request_with_retry(session: Any, url: str, attempts: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = session.get(url, timeout=60)
            if response.status_code == 429 or response.status_code >= 500:
                raise RuntimeError(f"HTTP {response.status_code} from {url}")
            response.raise_for_status()
            return response
        except Exception as exc:  # requests exceptions vary by installed version
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"Unable to fetch {url}: {last_error}") from last_error


def post_json_with_retry(
    session: Any,
    url: str,
    payload: dict[str, Any],
    attempts: int = 3,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = session.post(url, json=payload, timeout=60)
            if response.status_code == 429 or response.status_code >= 500:
                raise RuntimeError(f"HTTP {response.status_code} from {url}")
            response.raise_for_status()
            return response
        except Exception as exc:  # requests exceptions vary by installed version
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"Unable to POST {url}: {last_error}") from last_error


def load_rsc_models_with_retry(
    browser: Any,
    *,
    url: str,
    viewport: dict[str, int],
    extractor_js: str,
    parser: Callable[[str], list[dict[str, Any]]],
    label: str,
    attempts: int = 3,
    navigation_timeout_ms: int = 60_000,
    settle_timeout_ms: int = 5_000,
) -> list[dict[str, Any]]:
    """Load and parse an AA RSC payload, isolating every retry in a new context."""
    last_error: Exception | None = None
    for attempt in range(attempts):
        context = browser.new_context(user_agent=KIE_USER_AGENT, viewport=viewport)
        try:
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=navigation_timeout_ms)
            page.wait_for_timeout(settle_timeout_ms)
            script_text = page.evaluate(extractor_js)
            if not script_text:
                raise RuntimeError(f"AA {label} inline RSC script was not found")
            return parser(script_text)
        except Exception as exc:
            last_error = exc
        finally:
            context.close()
        if attempt + 1 < attempts:
            time.sleep(2**attempt)
    raise RuntimeError(
        f"AA {label} RSC extraction failed after {attempts} attempts: {last_error}"
    ) from last_error


def decode_rsc_string(encoded: str) -> str:
    try:
        return json.loads(f'"{encoded}"')
    except json.JSONDecodeError:
        return bytes(encoded, "utf-8").decode("unicode_escape")


def strip_rsc_prefix(decoded: str) -> str:
    """Strip a single-letter RSC flight-stream prefix such as ``c:`` or ``d:``.

    Next.js prefixes each inline flight payload with a kind letter and colon;
    the letter has changed across versions (``c:`` -> ``d:``).  Handle any
    one-letter prefix so a site upgrade cannot silently empty the payload.
    """
    if len(decoded) >= 2 and decoded[0].isalpha() and decoded[1] == ":":
        return decoded[2:]
    return decoded
















def find_intelligence_models_payload(value: Any) -> list[dict[str, Any]] | None:
    """Find AA's complete language-model context inside a decoded RSC payload."""
    if isinstance(value, dict):
        models = value.get("models")
        if isinstance(models, list) and any(
            isinstance(item, dict)
            and "intelligenceIndex" in item
            and "intelligenceIndexCostPerTask" in item
            for item in models
        ):
            return [item for item in models if isinstance(item, dict)]
        for child in value.values():
            found = find_intelligence_models_payload(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_intelligence_models_payload(child)
            if found:
                return found
    return None


def find_current_intelligence_models(value: Any) -> list[dict[str, Any]]:
    """Collect page-specific models that AA may omit from its global catalog."""
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        current = value.get("currentModel")
        if (
            isinstance(current, dict)
            and "intelligenceIndex" in current
            and "intelligenceIndexCostPerTask" in current
        ):
            found.append(current)
        for child in value.values():
            found.extend(find_current_intelligence_models(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(find_current_intelligence_models(child))
    return found


def parse_intelligence_rsc(script_text: str) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] | None = None
    current_models: list[dict[str, Any]] = []
    for match in RSC_PUSH_PATTERN.finditer(script_text):
        decoded = strip_rsc_prefix(decode_rsc_string(match.group(1)))
        try:
            payload = json.loads(decoded)
        except json.JSONDecodeError:
            continue
        if catalog is None:
            catalog = find_intelligence_models_payload(payload)
        current_models.extend(find_current_intelligence_models(payload))
    if catalog is None:
        raise RuntimeError("AA Intelligence RSC payload did not contain a models array")

    merged = list(catalog)
    positions = {
        str(model.get("slug") or model.get("id") or model.get("name")): index
        for index, model in enumerate(merged)
    }
    for model in current_models:
        identity = str(model.get("slug") or model.get("id") or model.get("name"))
        if identity in positions:
            merged[positions[identity]] = model
        else:
            positions[identity] = len(merged)
            merged.append(model)
    return merged


def build_intelligence_records(raw_models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for model in raw_models:
        score = finite_number(model.get("intelligenceIndex"))
        if score is None:
            continue
        cost_per_task = model.get("intelligenceIndexCostPerTask") or {}
        cost = finite_number((cost_per_task.get("cost") or {}).get("total"))
        slug = str(model.get("slug") or "").strip() or None
        records.append(
            {
                "name": model.get("shortName") or model.get("name") or slug,
                "slug": slug,
                "intelligence_index": score,
                "aa_cost_per_task_intelligence_usd": cost,
                "intelligence_source_url": AA_MODEL_URL.format(slug) if slug else None,
                "intelligence_status": "ok" if cost is not None and cost > 0 else "missing_cost",
            }
        )
    if not records:
        raise RuntimeError("AA Intelligence extraction returned no usable records")
    return records


def validate_intelligence_anchor(
    records: list[dict[str, Any]], anchor_slug: str
) -> None:
    if not any(row.get("slug") == anchor_slug for row in records):
        raise RuntimeError(
            f"AA Intelligence anchor model {anchor_slug} is missing from extracted records"
        )




def scrape_intelligence(anchor_slug: str) -> list[dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for AA extraction") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        try:
            raw_models = load_rsc_models_with_retry(
                browser,
                url=AA_MODEL_URL.format(anchor_slug),
                viewport={"width": 1400, "height": 1000},
                extractor_js="""
                () => Array.from(document.querySelectorAll('script:not([src])'))
                  .map(s => s.textContent || '')
                  .find(t => t.includes('intelligenceIndexCostPerTask') &&
                             t.includes('intelligenceIndex')) || ''
                """,
                parser=parse_intelligence_rsc,
                label="Intelligence",
            )
        finally:
            browser.close()
    records = build_intelligence_records(raw_models)
    validate_intelligence_anchor(records, anchor_slug)
    return records


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def model_key(name: str, slug: str | None = None) -> str:
    return f"{slug or ''}::{normalize(name)}"








def merge_intelligence_rows(
    intelligence: list[dict[str, Any]], retrieved_at: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for intel in intelligence:
        label = str(intel.get("name") or "").strip()
        if not label:
            continue
        slug = intel.get("slug")
        rows.append(
            {
                "model_id": model_key(label, slug),
                "name": label,
                "slug": slug,
                "intelligence_index": intel.get("intelligence_index"),
                "aa_cost_per_task_intelligence_usd": intel.get(
                    "aa_cost_per_task_intelligence_usd"
                ),
                "intelligence_source_url": intel.get("intelligence_source_url"),
                "intelligence_status": intel.get("intelligence_status"),
                "retrieved_at": retrieved_at,
            }
        )
    return rows


KIE_PAGE_FAMILY = {
    "gpt-5-6": "gpt-5-6",
    "gpt-5-5": "gpt-5-5",
    "claude-opus-5": "claude-opus-5",
    "grok-4-6": "grok-4-6",
    "gemini-3-7-flash": "gemini-3-7-flash",
    "grok-4-5": "grok-4-5",
    "claude-opus-4-7": "claude-opus-4-7",
    "claude-opus-4-8": "claude-opus-4-8",
    "claude-sonnet-5": "claude-sonnet-5",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
}


def kie_page_slug(model_slug: str | None) -> str | None:
    if not model_slug:
        return None
    for prefix, page in sorted(KIE_PAGE_FAMILY.items(), key=lambda item: -len(item[0])):
        if model_slug == prefix or model_slug.startswith(prefix + "-"):
            return page
    return None


def decode_html_json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace("\\n", " ").replace('\\"', '"')


def parse_money(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_kie_description(desc: str) -> dict[str, Any]:
    number = r"[\d,]+(?:\.\d+)?"
    rates: dict[str, float | None] = {
        "input": None,
        "cached_input": None,
        "cache_write": None,
        "output": None,
    }
    patterns = {
        "cached_input": rf"Cached Input\s+{number}\s+credits?[^$]{{0,80}}\$({number})",
        "cache_write": rf"Cache Writes?\s+{number}\s+credits?[^$]{{0,80}}\$({number})",
        "input": rf"(?<!Cached )\bInput\s+{number}\s+credits?[^$]{{0,80}}\$({number})",
        "output": rf"Output\s+{number}\s+credits?[^$]{{0,80}}\$({number})",
    }
    for field, pattern in patterns.items():
        match = re.search(pattern, desc, flags=re.I)
        if match:
            rates[field] = parse_money(match.group(1))

    claim: float | None = None
    match = re.search(r"([\d.]+)%\s+cheaper", desc, flags=re.I)
    if match:
        claim = parse_money(match.group(1))
    else:
        match = re.search(r"([\d.]+)%\s+of official", desc, flags=re.I)
        if match:
            claim = 100.0 - (parse_money(match.group(1)) or 0.0)

    topup = None
    match = re.search(r"\+([\d.]+)%\s+bonus", desc, flags=re.I)
    if match:
        topup = parse_money(match.group(1))

    exact_rates = rates["input"] is not None and rates["output"] is not None
    return {
        "pricing_desc": desc.strip(),
        "kie_input_price_1m_usd": rates["input"],
        "kie_cached_input_price_1m_usd": rates["cached_input"],
        "kie_cache_write_price_1m_usd": rates["cache_write"],
        "kie_output_price_1m_usd": rates["output"],
        "kie_claimed_discount_pct": claim,
        "kie_topup_bonus_pct": topup,
        "kie_pricing_status": "verified_rates" if exact_rates else "unverified",
    }


def parse_gpt56_official_rates(page_html: str) -> dict[str, dict[str, float]]:
    """Extract the public Sol/Terra/Luna official price table when present."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", page_html))
    text = re.sub(r"\s+", " ", text)
    marker = re.search(r"OpenAI Official Input Price", text, flags=re.I)
    output_marker = re.search(r"OpenAI Official Output Price", text, flags=re.I)
    if not marker or not output_marker or output_marker.start() <= marker.end():
        return {}
    input_values = [
        parse_money(value)
        for value in re.findall(r"\$([\d.]+)", text[marker.end() : output_marker.start()])
    ]
    output_tail = text[output_marker.end() : output_marker.end() + 250]
    output_values = [parse_money(value) for value in re.findall(r"\$([\d.]+)", output_tail)]
    names = ("gpt-5-6-sol", "gpt-5-6-terra", "gpt-5-6-luna")
    if len(input_values) < 3 or len(output_values) < 3:
        return {}
    return {
        name: {"official_input": input_values[index], "official_output": output_values[index]}
        for index, name in enumerate(names)
    }


def parse_kie_group_data(page_html: str, source_url: str) -> dict[str, dict[str, Any]]:
    pattern = re.compile(
        r'"userPath":"(?P<model>[^"]+)".{0,2500}?'
        r'"pricingDesc":"(?P<desc>(?:\\.|[^"\\])*)"',
        flags=re.S,
    )
    entries: dict[str, dict[str, Any]] = {}
    official_rates = parse_gpt56_official_rates(page_html)
    for match in pattern.finditer(page_html):
        model = match.group("model")
        desc = decode_html_json_string(match.group("desc"))
        if model in entries:
            continue
        entry = {"kie_model": model, "kie_source_url": source_url}
        entry.update(parse_kie_description(desc))
        if model in official_rates:
            entry.update(
                {
                    "published_official_input_price_1m_usd": official_rates[model][
                        "official_input"
                    ],
                    "published_official_output_price_1m_usd": official_rates[model][
                        "official_output"
                    ],
                    "official_rate_source": "kie_public_model_page",
                }
            )
        entries[model] = entry
    return entries


def normalize_kie_model_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def parse_kie_catalog_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize the public Kie pricing-table API into the page-entry contract.

    The visible pricing page is backed by this endpoint.  Its records are one
    row per model/charge direction, so they must be grouped before enrichment.
    This is deliberately independent of the model-page HTML parser: model
    pages can expose a placeholder such as ``wocx`` while the pricing table
    still contains exact input/output rates.
    """
    data = payload.get("data") or {}
    records = data.get("records") or []
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        description = str(record.get("modelDescription") or "").strip()
        if not description:
            continue
        model_name = description.split(",", 1)[0].strip()
        model = normalize_kie_model_slug(model_name)
        if not model:
            continue
        if not any(
            model == prefix or model.startswith(prefix + "-")
            for prefix in KIE_PAGE_FAMILY
        ):
            continue

        entry = grouped.setdefault(
            model,
            {
                "kie_model": model,
                "kie_source_url": record.get("anchor") or KIE_URL.format(model),
                "_pricing_parts": [],
            },
        )
        entry["_pricing_parts"].append(description)
        price = parse_money(str(record.get("usdPrice") or ""))
        official = parse_money(str(record.get("falPrice") or ""))
        lower = description.casefold()
        if "cached input" in lower:
            price_field = "kie_cached_input_price_1m_usd"
            official_field = "published_official_cached_input_price_1m_usd"
        elif "cache write" in lower:
            price_field = "kie_cache_write_price_1m_usd"
            official_field = "published_official_cache_write_price_1m_usd"
        elif re.search(r"\boutput\b", lower):
            price_field = "kie_output_price_1m_usd"
            official_field = "published_official_output_price_1m_usd"
        elif re.search(r"\binput\b", lower):
            price_field = "kie_input_price_1m_usd"
            official_field = "published_official_input_price_1m_usd"
        else:
            continue
        entry[price_field] = price
        if official is not None:
            entry[official_field] = official
        discount = parse_money(str(record.get("discountRate") or ""))
        if discount is not None:
            entry["kie_claimed_discount_pct"] = discount

    entries: dict[str, dict[str, Any]] = {}
    for model, entry in grouped.items():
        entry["pricing_desc"] = "; ".join(entry.pop("_pricing_parts", []))
        exact_rates = (
            entry.get("kie_input_price_1m_usd") is not None
            and entry.get("kie_output_price_1m_usd") is not None
        )
        entry["kie_pricing_status"] = "verified_rates" if exact_rates else "unverified"
        entries[model] = entry
    return entries


def scrape_kie_catalog(session: Any) -> dict[str, dict[str, Any]]:
    """Fetch every page of Kie's public model-pricing table."""
    page_size = 100
    first_payload = {
        "pageNum": 1,
        "pageSize": page_size,
        "modelDescription": "",
        "interfaceType": "",
    }
    first_response = post_json_with_retry(session, KIE_API_URL, first_payload)
    first = first_response.json()
    data = first.get("data") or {}
    records = list(data.get("records") or [])
    pages = int(data.get("pages") or 1)
    for page_num in range(2, pages + 1):
        payload = dict(first_payload)
        payload["pageNum"] = page_num
        response = post_json_with_retry(session, KIE_API_URL, payload)
        page = response.json()
        records.extend((page.get("data") or {}).get("records") or [])
    return parse_kie_catalog_payload({"data": {"records": records}})


def scrape_kie_pages(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("requests is required for Kie.ai pricing extraction") from exc

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": KIE_USER_AGENT,
            "Accept": "application/json, text/html",
            "Origin": "https://kie.ai",
            "Referer": "https://kie.ai/pricing",
        }
    )
    page_slugs = sorted({kie_page_slug(row.get("slug")) for row in rows if kie_page_slug(row.get("slug"))})
    all_entries: dict[str, dict[str, Any]] = {}
    try:
        all_entries.update(scrape_kie_catalog(session))
    except Exception as exc:
        all_entries["__catalog_error__"] = {
            "kie_model": "pricing-catalog",
            "kie_source_url": KIE_API_URL,
            "kie_pricing_status": "fetch_error",
            "kie_error": str(exc),
        }
    for page_slug in page_slugs:
        url = KIE_URL.format(page_slug)
        try:
            response = request_with_retry(session, url)
            entries = parse_kie_group_data(response.text, url)
            for model, entry in entries.items():
                existing = all_entries.get(model)
                if not existing or existing.get("kie_pricing_status") != "verified_rates":
                    all_entries[model] = entry
        except Exception as exc:
            all_entries[f"__page_error__:{page_slug}"] = {
                "kie_model": page_slug,
                "kie_source_url": url,
                "kie_pricing_status": "fetch_error",
                "kie_error": str(exc),
            }
    return all_entries


def enrich_with_kie(rows: list[dict[str, Any]], entries: dict[str, dict[str, Any]]) -> None:
    for row in rows:
        kie_model = row.get("slug")
        if not kie_model:
            row["kie_pricing_status"] = "not_mapped"
            continue
        entry_key = kie_model if kie_model in entries else None
        if entry_key is None:
            # AA appends reasoning tiers to one provider model slug. Kie prices
            # are published at the family slug, so inherit only from an exact
            # family prefix rather than applying a global discount.
            family_candidates = [
                key
                for key in entries
                if not key.startswith("__page_error__:")
                and kie_model.startswith(key + "-")
            ]
            if family_candidates:
                entry_key = max(family_candidates, key=len)
        entry = entries.get(entry_key) if entry_key else None
        if entry is None:
            row["kie_pricing_status"] = "not_found"
            row["kie_model_page"] = kie_page_slug(kie_model)
            continue
        row.update({f"{key}": value for key, value in entry.items()})
        row["kie_model"] = entry.get("kie_model")
        row["kie_model_page"] = kie_page_slug(kie_model)

        aa_input = finite_number(row.get("aa_price_input_1m_usd"))
        aa_output = finite_number(row.get("aa_price_output_1m_usd"))
        kie_input = finite_number(row.get("kie_input_price_1m_usd"))
        kie_output = finite_number(row.get("kie_output_price_1m_usd"))
        if aa_input and aa_output and kie_input is not None and kie_output is not None:
            aa_blended = (3 * aa_input + aa_output) / 4
            kie_blended = (3 * kie_input + kie_output) / 4
            if aa_blended > 0:
                ratio = kie_blended / aa_blended
                row["kie_vs_aa_reference_blended_delta_pct"] = (ratio - 1) * 100
                for cost_field, out_field in (
                    (
                        "aa_cost_per_task_intelligence_usd",
                        "kie_reference_cost_per_task_intelligence_usd",
                    ),
                ):
                    cost = finite_number(row.get(cost_field))
                    row[out_field] = cost * ratio if cost is not None else None

        official_input = finite_number(row.get("published_official_input_price_1m_usd"))
        official_output = finite_number(row.get("published_official_output_price_1m_usd"))
        computed_discount: float | None = None
        nominal_ratio: float | None = None
        if official_input and official_output and kie_input is not None and kie_output is not None:
            official_blended = (3 * official_input + official_output) / 4
            kie_blended = (3 * kie_input + kie_output) / 4
            if official_blended > 0:
                nominal_ratio = kie_blended / official_blended
                computed_discount = (1 - nominal_ratio) * 100
                row["kie_nominal_discount_vs_published_official_pct"] = computed_discount
        elif row.get("kie_claimed_discount_pct") is not None:
            computed_discount = finite_number(row["kie_claimed_discount_pct"])
            row["kie_nominal_discount_vs_published_official_pct"] = computed_discount
            nominal_ratio = 1 - computed_discount / 100 if computed_discount is not None else None

        claimed_discount = finite_number(row.get("kie_claimed_discount_pct"))
        if computed_discount is not None and claimed_discount is not None:
            delta = computed_discount - claimed_discount
            row["kie_claimed_vs_computed_discount_delta_pp"] = delta
            row["kie_pricing_consistency"] = "consistent" if abs(delta) <= 2 else "conflict"
        elif computed_discount is not None:
            row["kie_pricing_consistency"] = "computed_only"
        elif claimed_discount is not None:
            row["kie_pricing_consistency"] = "claim_only"
        else:
            row["kie_pricing_consistency"] = "rates_only"

        bonus = finite_number(row.get("kie_topup_bonus_pct"))
        if nominal_ratio is not None and bonus is not None and bonus > 0:
            row["kie_effective_discount_with_topup_pct"] = (
                1 - nominal_ratio / (1 + bonus / 100)
            ) * 100


def compact_frontier_row(row: dict[str, Any], score_field: str, cost_field: str) -> dict[str, Any]:
    score = finite_number(row.get(score_field))
    cost = finite_number(row.get(cost_field))
    kie_task_fields = {
        "aa_cost_per_task_intelligence_usd": "kie_reference_cost_per_task_intelligence_usd",
    }
    if cost_field.startswith("kie_reference_cost_per_task_"):
        kie_cost = cost
        aa_cost_field = cost_field.replace(
            "kie_reference_cost_per_task_", "aa_cost_per_task_", 1
        )
        aa_cost = finite_number(row.get(aa_cost_field))
    else:
        kie_cost = finite_number(row.get(kie_task_fields.get(cost_field, "")))
        aa_cost = cost
    kie_reduction = None
    if aa_cost is not None and aa_cost > 0 and kie_cost is not None:
        kie_reduction = (1 - kie_cost / aa_cost) * 100
    return {
        "model": row.get("name"),
        "slug": row.get("slug"),
        "score": score,
        "cost_per_task_usd": cost,
        "score_per_dollar": score / cost if score is not None and cost else None,
        "kie_cost_per_task_usd": kie_cost,
        "kie_cost_reduction_vs_aa_pct": kie_reduction,
        "kie_source_url": row.get("kie_source_url"),
        "kie_nominal_discount_pct": row.get("kie_nominal_discount_vs_published_official_pct"),
        "kie_claimed_discount_pct": row.get("kie_claimed_discount_pct"),
        "kie_input_price_1m_usd": row.get("kie_input_price_1m_usd"),
        "kie_output_price_1m_usd": row.get("kie_output_price_1m_usd"),
        "kie_vs_aa_reference_blended_delta_pct": row.get("kie_vs_aa_reference_blended_delta_pct"),
        "kie_pricing_consistency": row.get("kie_pricing_consistency"),
        "kie_pricing_status": row.get("kie_pricing_status"),
    }


def _log_cost_slope(
    left: dict[str, Any],
    right: dict[str, Any],
    score_field: str,
    cost_field: str,
) -> float:
    left_score = finite_number(left.get(score_field)) or 0.0
    right_score = finite_number(right.get(score_field)) or 0.0
    left_cost = finite_number(left.get(cost_field)) or 0.0
    right_cost = finite_number(right.get(cost_field)) or 0.0
    delta_log_cost = math.log(right_cost) - math.log(left_cost)
    if delta_log_cost <= 0:
        return float("inf")
    return (right_score - left_score) / delta_log_cost


def supported_frontier(
    frontier: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
) -> list[dict[str, Any]]:
    """Keep supported Pareto points on score versus logarithmic cost.

    Strict Pareto points can still be economically redundant. The upper
    concave envelope keeps only points that are optimal for some trade-off
    between score and proportional cost. Interior marginal slopes must
    decrease as cost rises; collinear or below-envelope points are removed.
    """
    hull: list[dict[str, Any]] = []
    for row in frontier:
        cost = finite_number(row.get(cost_field))
        score = finite_number(row.get(score_field))
        if cost is None or cost <= 0 or score is None:
            continue
        if hull:
            previous_cost = finite_number(hull[-1].get(cost_field)) or 0.0
            if math.isclose(cost, previous_cost, rel_tol=1e-12, abs_tol=0.0):
                previous_score = finite_number(hull[-1].get(score_field)) or 0.0
                if score > previous_score:
                    hull[-1] = row
                continue
        while len(hull) >= 2:
            incoming = _log_cost_slope(hull[-2], hull[-1], score_field, cost_field)
            outgoing = _log_cost_slope(hull[-1], row, score_field, cost_field)
            if incoming > outgoing + 1e-12:
                break
            hull.pop()
        hull.append(row)
    return hull


def standout_frontier(
    frontier: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
    minimum_knee_strength: float = 2.0,
) -> list[dict[str, Any]]:
    """Keep endpoints and local knees relative to strict-frontier neighbors."""
    if len(frontier) <= 2:
        return list(frontier)
    selected = [frontier[0]]
    for index in range(1, len(frontier) - 1):
        incoming = _log_cost_slope(
            frontier[index - 1], frontier[index], score_field, cost_field
        )
        outgoing = _log_cost_slope(
            frontier[index], frontier[index + 1], score_field, cost_field
        )
        if outgoing > 0 and incoming / outgoing >= minimum_knee_strength:
            selected.append(frontier[index])
    selected.append(frontier[-1])
    return selected


def select_value_anchor(
    supported: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
) -> dict[str, Any]:
    """Select the strongest global knee on the supported Pareto frontier."""
    eligible = [
        row
        for row in supported
        if finite_number(row.get(score_field)) is not None
        and (finite_number(row.get(cost_field)) or 0) > 0
    ]
    if not eligible:
        raise ValueError("Cannot select a value anchor from an empty frontier")
    if len(eligible) < 3:
        return max(
            eligible,
            key=lambda row: (finite_number(row.get(score_field)) or 0)
            / (finite_number(row.get(cost_field)) or float("inf")),
        )

    knees: list[tuple[float, dict[str, Any]]] = []
    for index in range(1, len(eligible) - 1):
        incoming = _log_cost_slope(
            eligible[index - 1], eligible[index], score_field, cost_field
        )
        outgoing = _log_cost_slope(
            eligible[index], eligible[index + 1], score_field, cost_field
        )
        if outgoing > 0:
            knees.append((incoming / outgoing, eligible[index]))
    if knees:
        return max(knees, key=lambda item: item[0])[1]
    return max(
        eligible,
        key=lambda row: (finite_number(row.get(score_field)) or 0)
        / (finite_number(row.get(cost_field)) or float("inf")),
    )


def build_upgrade_ladder(
    strict: list[dict[str, Any]],
    value_anchor: dict[str, Any],
    score_field: str,
    cost_field: str,
    display_cost_field: str | None = None,
) -> dict[str, Any]:
    """Build the raw-cost concave envelope above a global value anchor."""
    rendered_cost_field = display_cost_field or cost_field
    anchor_score = finite_number(value_anchor.get(score_field))
    anchor_cost = finite_number(value_anchor.get(cost_field))
    if anchor_score is None or anchor_score <= 0 or anchor_cost is None or anchor_cost <= 0:
        raise ValueError("Value anchor must have positive score and cost")

    ordered = sorted(
        strict,
        key=lambda row: (
            finite_number(row.get(cost_field)) or float("inf"),
            -(finite_number(row.get(score_field)) or 0),
        ),
    )
    candidates = [value_anchor] + [
        row
        for row in ordered
        if row is not value_anchor
        and (finite_number(row.get(cost_field)) or 0) > anchor_cost
        and (finite_number(row.get(score_field)) or 0) > anchor_score
    ]

    def marginal_return(left: dict[str, Any], right: dict[str, Any]) -> float:
        left_score = finite_number(left.get(score_field)) or 0
        right_score = finite_number(right.get(score_field)) or 0
        left_cost = finite_number(left.get(cost_field)) or 0
        right_cost = finite_number(right.get(cost_field)) or 0
        cost_delta = right_cost - left_cost
        return (right_score - left_score) / cost_delta if cost_delta > 0 else float("inf")

    selected: list[dict[str, Any]] = []
    removed_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        while len(selected) >= 2:
            previous = selected[-2]
            middle = selected[-1]
            incoming = marginal_return(previous, middle)
            outgoing = marginal_return(middle, candidate)
            if incoming > outgoing + 1e-12:
                break
            removed_rows.append(selected.pop())
        selected.append(candidate)

    removed: list[dict[str, Any]] = []
    for middle in sorted(
        removed_rows,
        key=lambda row: finite_number(row.get(cost_field)) or float("inf"),
    ):
        middle_cost = finite_number(middle.get(cost_field)) or 0
        cheaper = [
            row
            for row in selected
            if (finite_number(row.get(cost_field)) or 0) < middle_cost
        ]
        dearer = [
            row
            for row in selected
            if (finite_number(row.get(cost_field)) or 0) > middle_cost
        ]
        if not cheaper or not dearer:
            continue
        previous = cheaper[-1]
        next_row = dearer[0]
        rendered = compact_frontier_row(middle, score_field, rendered_cost_field)
        rendered.update(
            {
                "previous_model": previous.get("name"),
                "next_model": next_row.get("name"),
                "incoming_marginal_score_per_dollar": marginal_return(
                    previous, middle
                ),
                "outgoing_marginal_score_per_dollar": marginal_return(
                    middle, next_row
                ),
                "bypass_marginal_score_per_dollar": marginal_return(
                    previous, next_row
                ),
                "removal_reason": (
                    "marginal return rises after this point; the next retained "
                    "model offers a more efficient incremental upgrade"
                ),
            }
        )
        removed.append(rendered)

    tiers: list[dict[str, Any]] = []
    previous_marginal: float | None = None
    for index, row in enumerate(selected):
        score = finite_number(row.get(score_field)) or 0
        cost = finite_number(row.get(cost_field)) or 0
        previous = selected[index - 1] if index else None
        previous_score = finite_number(previous.get(score_field)) if previous else None
        previous_cost = finite_number(previous.get(cost_field)) if previous else None
        cost_multiple = cost / anchor_cost
        uplift_pct = (score / anchor_score - 1) * 100
        marginal = marginal_return(previous, row) if previous else None
        rendered = compact_frontier_row(row, score_field, rendered_cost_field)
        rendered.update(
            {
                "tier_type": (
                    "value_anchor"
                    if index == 0
                    else "quality_ceiling"
                    if index + 1 == len(selected)
                    else "marginal_upgrade"
                ),
                "actual_uplift_pct_from_anchor": uplift_pct,
                "score_gain_from_anchor": score - anchor_score,
                "cost_multiple_from_anchor": cost_multiple,
                "performance_uplift_pct_per_cost_doubling_from_anchor": (
                    uplift_pct / math.log2(cost_multiple)
                    if cost_multiple > 1
                    else None
                ),
                "previous_tier": previous.get("name") if previous else None,
                "score_gain_from_previous_tier": (
                    score - previous_score if previous_score is not None else None
                ),
                "cost_increase_from_previous_tier_usd": (
                    cost - previous_cost if previous_cost is not None else None
                ),
                "cost_multiple_from_previous_tier": (
                    cost / previous_cost
                    if previous_cost is not None and previous_cost > 0
                    else None
                ),
                "marginal_score_per_dollar_from_previous": marginal,
                "incremental_cost_per_score_point": (
                    1 / marginal if marginal is not None and marginal > 0 else None
                ),
                "marginal_return_retained_vs_previous_segment_pct": (
                    marginal / previous_marginal * 100
                    if marginal is not None
                    and previous_marginal is not None
                    and previous_marginal > 0
                    else None
                ),
            }
        )
        tiers.append(rendered)
        if marginal is not None:
            previous_marginal = marginal

    return {
        "method": (
            "strongest knee on the global supported frontier, then upper concave "
            "envelope of score versus raw incremental task cost"
        ),
        "decision_rule": (
            "retain tiers only while marginal score gained per additional dollar "
            "decreases monotonically"
        ),
        "tiers": tiers,
        "quality_ceiling": tiers[-1] if tiers else None,
        "removed_by_marginal_return": removed,
    }


def compact_frontier_rows(
    rows: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        previous = rows[index - 1] if index else None
        next_row = rows[index + 1] if index + 1 < len(rows) else None
        score = finite_number(row.get(score_field)) or 0.0
        cost = finite_number(row.get(cost_field)) or 0.0
        result = compact_frontier_row(row, score_field, cost_field)

        previous_score = finite_number(previous.get(score_field)) if previous else None
        previous_cost = finite_number(previous.get(cost_field)) if previous else None
        next_score = finite_number(next_row.get(score_field)) if next_row else None
        next_cost = finite_number(next_row.get(cost_field)) if next_row else None

        result.update(
            {
                "previous_model": previous.get("name") if previous else None,
                "score_gain_vs_previous": (
                    score - previous_score if previous_score is not None else None
                ),
                "score_gain_vs_previous_pct": (
                    (score / previous_score - 1) * 100
                    if previous_score is not None and previous_score != 0
                    else None
                ),
                "cost_increase_vs_previous_usd": (
                    cost - previous_cost if previous_cost is not None else None
                ),
                "cost_multiple_vs_previous": (
                    cost / previous_cost
                    if previous_cost is not None and previous_cost > 0
                    else None
                ),
                "next_model": next_row.get("name") if next_row else None,
                "score_gain_to_next": next_score - score if next_score is not None else None,
                "score_gain_to_next_pct": (
                    (next_score / score - 1) * 100
                    if next_score is not None and score != 0
                    else None
                ),
                "cost_increase_to_next_usd": (
                    next_cost - cost if next_cost is not None else None
                ),
                "cost_multiple_to_next": (
                    next_cost / cost if next_cost is not None and cost > 0 else None
                ),
            }
        )
        incoming = (
            _log_cost_slope(previous, row, score_field, cost_field)
            if previous is not None
            else None
        )
        outgoing = (
            _log_cost_slope(row, next_row, score_field, cost_field)
            if next_row is not None
            else None
        )
        result["marginal_score_per_log_cost_from_previous"] = incoming
        result["marginal_score_per_log_cost_to_next"] = outgoing
        result["knee_strength"] = (
            incoming / outgoing
            if incoming is not None and outgoing is not None and outgoing > 0
            else None
        )
        public.append(result)
    return public


def epsilon_prune(
    frontier: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
    min_score_gain: float,
    max_cost_premium_pct: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Remove a cheaper frontier row when a near-priced, better row exists.

    A row is epsilon-dominated when another row improves the benchmark score by
    at least ``min_score_gain`` while costing no more than the configured
    percentage above the row being considered.  This is intentionally applied
    after strict Pareto calculation so the raw mathematical frontier remains
    available for inspection.
    """
    retained: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    cost_multiplier = 1 + max_cost_premium_pct / 100
    for row in frontier:
        score = finite_number(row.get(score_field))
        cost = finite_number(row.get(cost_field))
        dominated = (
            score is not None
            and cost is not None
            and any(
                (finite_number(other.get(score_field)) or 0) - score >= min_score_gain
                and (finite_number(other.get(cost_field)) or float("inf"))
                <= cost * cost_multiplier
                for other in frontier
                if other is not row
            )
        )
        (removed if dominated else retained).append(row)
    return retained, removed


def pragmatic_prune(
    rows: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
    min_gain: float,
    max_incremental_cost_per_score_point: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Filter low-gain and high-marginal-cost steps against retained neighbors.

    Each candidate is compared with the last retained row. Either rejection
    rebases the next candidate on the previous retained option, avoiding gaps
    in the comparison chain.
    """
    retained: list[dict[str, Any]] = []
    removed_by_min_gain: list[dict[str, Any]] = []
    removed_by_cost_inefficiency: list[dict[str, Any]] = []
    for row in rows:
        if not retained:
            retained.append(row)
            continue

        previous = retained[-1]
        previous_score = finite_number(previous.get(score_field))
        score = finite_number(row.get(score_field))
        previous_cost = finite_number(previous.get(cost_field))
        cost = finite_number(row.get(cost_field))
        score_gain = score - previous_score if score is not None and previous_score is not None else None
        cost_increase = cost - previous_cost if cost is not None and previous_cost is not None else None
        incremental_cost = (
            cost_increase / score_gain
            if score_gain is not None and score_gain > 0 and cost_increase is not None
            else None
        )

        if score_gain is None or score_gain < min_gain:
            removed_by_min_gain.append(row)
            continue

        if incremental_cost is not None and incremental_cost <= max_incremental_cost_per_score_point:
            retained.append(row)
            continue

        removed_by_cost_inefficiency.append(
            {
                "row": row,
                "previous_model": previous.get("name") or previous.get("model") or previous.get("slug"),
                "score_gain_from_previous": score_gain,
                "cost_increase_from_previous_usd": cost_increase,
                "incremental_cost_per_score_point": incremental_cost,
                "max_incremental_cost_per_score_point": max_incremental_cost_per_score_point,
                "removal_reason": "incremental cost per score point exceeds the configured cap",
            }
        )
    return retained, removed_by_min_gain, removed_by_cost_inefficiency


def make_frontier(
    rows: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
    minimum_score: float,
    min_gain: float,
    epsilon_score_gain: float,
    epsilon_cost_premium_pct: float,
    minimum_knee_strength: float,
    max_incremental_cost_per_score_point: float = 0.75,
) -> dict[str, Any]:
    eligible = [
        row
        for row in rows
        if finite_number(row.get(score_field)) is not None
        and (finite_number(row.get(cost_field)) or 0) > 0
        and finite_number(row.get(score_field)) > minimum_score
    ]
    strict: list[dict[str, Any]] = []
    for row in eligible:
        score = finite_number(row.get(score_field)) or 0
        cost = finite_number(row.get(cost_field)) or 0
        dominated = any(
            (finite_number(other.get(score_field)) or 0) >= score
            and (finite_number(other.get(cost_field)) or 0) <= cost
            and (
                (finite_number(other.get(score_field)) or 0) > score
                or (finite_number(other.get(cost_field)) or 0) < cost
            )
            for other in eligible
            if other is not row
        )
        if not dominated:
            strict.append(row)
    strict.sort(
        key=lambda row: (
            finite_number(row.get(cost_field)) or 0,
            -(finite_number(row.get(score_field)) or 0),
        )
    )
    supported = supported_frontier(strict, score_field, cost_field)
    if supported:
        value_anchor = select_value_anchor(supported, score_field, cost_field)
        upgrade_ladder = build_upgrade_ladder(
            strict,
            value_anchor,
            score_field,
            cost_field,
        )
    else:
        upgrade_ladder = {
            "method": (
                "strongest knee on the global supported frontier, then upper concave "
                "envelope of score versus raw incremental task cost"
            ),
            "decision_rule": (
                "retain tiers only while marginal score gained per additional dollar "
                "decreases monotonically"
            ),
            "tiers": [],
            "quality_ceiling": None,
            "removed_by_marginal_return": [],
        }
    standout = standout_frontier(
        strict, score_field, cost_field, minimum_knee_strength
    )
    epsilon, removed_by_epsilon = epsilon_prune(
        strict,
        score_field,
        cost_field,
        epsilon_score_gain,
        epsilon_cost_premium_pct,
    )
    pragmatic, removed_by_min_gain, removed_by_cost_inefficiency = pragmatic_prune(
        epsilon,
        score_field,
        cost_field,
        min_gain,
        max_incremental_cost_per_score_point,
    )

    def render_cost_removal(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            **compact_frontier_row(entry["row"], score_field, cost_field),
            **{key: value for key, value in entry.items() if key != "row"},
        }

    strict_public = compact_frontier_rows(strict, score_field, cost_field)
    standout_ids = {id(row) for row in standout}
    strict_public_by_id: dict[int, dict[str, Any]] = {}
    for row, rendered in zip(strict, strict_public):
        rendered["is_standout"] = id(row) in standout_ids
        strict_public_by_id[id(row)] = rendered

    standout_public = [dict(strict_public_by_id[id(row)]) for row in standout]
    for index, rendered in enumerate(standout_public):
        if len(standout_public) == 1:
            reason = "cheapest_and_highest_score_pareto_point"
        elif index == 0:
            reason = "cheapest_pareto_point"
        elif index + 1 == len(standout_public):
            reason = "highest_score_pareto_point"
        else:
            reason = "local_knee_vs_strict_frontier_neighbors"
        rendered["selection_reason"] = reason

    return {
        "score_field": score_field,
        "cost_field": cost_field,
        "minimum_score_exclusive": minimum_score,
        "minimum_gain": min_gain,
        "epsilon_score_gain": epsilon_score_gain,
        "epsilon_cost_premium_pct": epsilon_cost_premium_pct,
        "max_incremental_cost_per_score_point": max_incremental_cost_per_score_point,
        "strict_count": len(strict),
        "supported_count": len(supported),
        "standout_count": len(standout),
        "epsilon_count": len(epsilon),
        "pragmatic_count": len(pragmatic),
        "cost_inefficiency_count": len(removed_by_cost_inefficiency),
        "supported_method": "upper concave envelope of score versus natural-log cost",
        "standout_method": (
            "strict-frontier endpoints plus local knees where incoming/outgoing "
            f"marginal score-per-log-cost ratio is >= {minimum_knee_strength}"
        ),
        "upgrade_ladder": upgrade_ladder,
        "strict_frontier": strict_public,
        "supported_frontier": compact_frontier_rows(
            supported, score_field, cost_field
        ),
        "standout_frontier": standout_public,
        "epsilon_frontier": [
            compact_frontier_row(row, score_field, cost_field) for row in epsilon
        ],
        "pragmatic_frontier": [
            compact_frontier_row(row, score_field, cost_field) for row in pragmatic
        ],
        "removed_by_epsilon": [
            compact_frontier_row(row, score_field, cost_field)
            for row in removed_by_epsilon
        ],
        "removed_by_min_gain": [
            compact_frontier_row(row, score_field, cost_field)
            for row in removed_by_min_gain
        ],
        "removed_by_cost_inefficiency": [
            render_cost_removal(entry) for entry in removed_by_cost_inefficiency
        ],
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = [
        "name",
        "slug",
        "intelligence_index",
        "aa_cost_per_task_intelligence_usd",
        "kie_input_price_1m_usd",
        "kie_output_price_1m_usd",
        "kie_source_url",
        "kie_reference_cost_per_task_intelligence_usd",
        "kie_nominal_discount_vs_published_official_pct",
        "kie_claimed_discount_pct",
        "kie_effective_discount_with_topup_pct",
        "kie_vs_aa_reference_blended_delta_pct",
        "kie_pricing_consistency",
        "kie_pricing_status",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)



def fingerprint(payload: dict[str, Any]) -> str:
    stable = dict(payload)
    stable.pop("generated_at", None)
    stable.pop("sources", None)
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--anchor-slug", action="append", dest="anchors")
    parser.add_argument("--min-intel", type=float, default=35.0)
    parser.add_argument("--min-gain", type=float, default=0.5)
    parser.add_argument(
        "--min-knee-strength",
        type=float,
        default=2.0,
        help="Minimum incoming/outgoing marginal-return ratio for a standout knee",
    )
    parser.add_argument(
        "--epsilon-score-gain",
        type=float,
        default=0.5,
        help="Minimum score improvement for epsilon-dominance",
    )
    parser.add_argument(
        "--epsilon-cost-premium-pct",
        type=float,
        default=10.0,
        help="Maximum extra cost percentage allowed for epsilon-dominance",
    )
    parser.add_argument(
        "--max-incremental-cost-per-score-point",
        type=float,
        default=0.75,
        help="Maximum marginal benchmark-task cost in USD per additional Index point",
    )
    parser.add_argument(
        "--with-kie",
        action="store_true",
        help="Opt in to public Kie.ai pricing checks (AA-only by default)",
    )
    parser.add_argument(
        "--no-kie",
        action="store_true",
        help="Deprecated compatibility flag; Kie.ai checks are already off by default",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()



def run(args: argparse.Namespace) -> tuple[dict[str, Any], bool, Path]:
    retrieved_at = now_iso()
    anchors = tuple(args.anchors or DEFAULT_ANCHORS)
    intelligence: list[dict[str, Any]] | None = None
    intelligence_anchor: str | None = None
    intel_error: str | None = None
    for anchor in anchors:
        try:
            intelligence = scrape_intelligence(anchor)
            intelligence_anchor = anchor
            break
        except Exception as exc:
            intel_error = str(exc)
    if intelligence is None:
        raise RuntimeError(f"All AA Intelligence anchors failed: {intel_error}")

    rows = merge_intelligence_rows(intelligence, retrieved_at)
    kie_entries: dict[str, dict[str, Any]] = {}
    if args.with_kie and not args.no_kie:
        kie_entries = scrape_kie_pages(rows)
        enrich_with_kie(rows, kie_entries)
    else:
        for row in rows:
            row["kie_pricing_status"] = "skipped"

    payload: dict[str, Any] = {
        "schema_version": 10,
        "generated_at": retrieved_at,
        "sources": {
            "aa_intelligence_context_url": (
                AA_MODEL_URL.format(intelligence_anchor) if intelligence_anchor else None
            ),
            "kie_pricing_catalog_url": KIE_API_URL,
            "kie_pages_checked": sorted(
                {
                    entry.get("kie_source_url")
                    for entry in kie_entries.values()
                    if entry.get("kie_source_url")
                }
            ),
        },
        "policy": {
            "intelligence_minimum_exclusive": args.min_intel,
            "minimum_gain": args.min_gain,
            "minimum_knee_strength": args.min_knee_strength,
            "upgrade_ladder_method": "raw_cost_marginal_return_concave_envelope",
            "epsilon_score_gain": args.epsilon_score_gain,
            "epsilon_cost_premium_pct": args.epsilon_cost_premium_pct,
            "max_incremental_cost_per_score_point": args.max_incremental_cost_per_score_point,
            "pragmatic_frontier_policy": (
                "after epsilon and minimum-gain pruning, keep a step only when its "
                "incremental AA benchmark-task cost from the last retained model is "
                "no more than the configured USD per Index point cap"
            ),
            "cost_semantics": {
                "aa_cost_per_task_intelligence_usd": "AA Intelligence Index benchmark task",
                "kie_reference_cost": "AA Intelligence task cost translated with Kie/AA blended token-price ratio; estimate only",
            },
            "frontier_columns": {
                "score_per_dollar": "Index points per AA dollar per benchmark task",
                "kie_cost_per_task_usd": "Estimated same benchmark task cost through Kie.ai",
                "kie_cost_reduction_vs_aa_pct": "Reduction of estimated Kie task cost versus AA task cost",
                "knee_strength": "Incoming marginal score/log-cost slope divided by outgoing slope",
            },
        },
        "counts": {
            "aa_intelligence_models": len(intelligence),
            "merged_rows": len(rows),
            "kie_verified_rows": sum(
                row.get("kie_pricing_status") == "verified_rates" for row in rows
            ),
            "kie_unverified_rows": sum(
                row.get("kie_pricing_status") == "unverified" for row in rows
            ),
        },
        "data": rows,
        "frontiers": {
            "intelligence_aa": make_frontier(
                rows,
                "intelligence_index",
                "aa_cost_per_task_intelligence_usd",
                args.min_intel,
                args.min_gain,
                args.epsilon_score_gain,
                args.epsilon_cost_premium_pct,
                args.min_knee_strength,
                args.max_incremental_cost_per_score_point,
            ),
        },
    }
    payload["fingerprint"] = fingerprint(payload)

    output_dir = args.output_dir or default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "latest.json", payload)
    write_json(
        output_dir / "raw-intelligence.json",
        {"retrieved_at": retrieved_at, "data": intelligence},
    )
    write_json(output_dir / "kie-pricing.json", {"retrieved_at": retrieved_at, "data": kie_entries})
    write_rows_csv(output_dir / "latest.csv", rows)
    history_dir = output_dir / "history"
    write_json(history_dir / f"{datetime.now(timezone.utc):%Y-%m-%d}.json", payload)

    previous_path = output_dir / "previous-fingerprint.txt"
    old = previous_path.read_text(encoding="utf-8").strip() if previous_path.exists() else ""
    changed = old != payload["fingerprint"]
    previous_path.write_text(payload["fingerprint"] + "\n", encoding="utf-8")
    return payload, changed, output_dir



def main() -> int:
    args = parse_args()
    if args.min_gain < 0 or args.epsilon_score_gain < 0:
        print("AA Pareto refresh ERROR: score thresholds must be >= 0", file=sys.stderr)
        return 1
    if args.min_knee_strength < 1:
        print("AA Pareto refresh ERROR: knee strength must be >= 1", file=sys.stderr)
        return 1

    if args.epsilon_cost_premium_pct < 0:
        print("AA Pareto refresh ERROR: epsilon cost premium must be >= 0", file=sys.stderr)
        return 1
    if args.max_incremental_cost_per_score_point < 0:
        print(
            "AA Pareto refresh ERROR: maximum incremental cost per score point must be >= 0",
            file=sys.stderr,
        )
        return 1
    try:
        payload, changed, output_dir = run(args)
    except Exception as exc:
        print(f"AA Pareto refresh ERROR: {exc}", file=sys.stderr)
        return 1
    if not args.quiet:
        counts = payload["counts"]
        print(
            "AA Pareto refreshed: "
            f"{counts['aa_intelligence_models']} intelligence / "
            f"{counts['kie_verified_rows']} Kie verified; "
            f"changed={'yes' if changed else 'no'}; "
            f"output={output_dir}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

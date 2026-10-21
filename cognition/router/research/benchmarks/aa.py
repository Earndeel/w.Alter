"""Artificial Analysis Intelligence Index and its cost per task, per model x reasoning level. Read from the
Next.js flight data of an AA model page (the page carries AA's whole language-model context), no browser. Parsing
taken over from the aa-pareto-model-optimizer skill on 2026-10-21 (Kie enrichment and the skill's own frontier are
not needed: prices come from research.prices, frontiers from analysis.pareto)."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Any

from walter_router.research.web import fetch_text, now

AA_MODEL_URL = "https://artificialanalysis.ai/models/{}"
# Any AA model page carries the full catalogue; several anchors in case one page is retired.
ANCHORS = ("gpt-6-luna", "gpt-5-6-luna", "claude-opus-5-5", "deepseek-v4-pro")
MIN_MODELS = 300    # a smaller parse means the page changed: keep the last good snapshot


RSC_PUSH_PATTERN = re.compile(
    r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)'
)


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


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


def records(raw_models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for model in raw_models:
        score = finite_number(model.get("intelligenceIndex"))
        if score is None:
            continue
        cost = finite_number(((model.get("intelligenceIndexCostPerTask") or {}).get("cost") or {}).get("total"))
        slug = str(model.get("slug") or "").strip() or None
        out.append({"name": model.get("shortName") or model.get("name") or slug, "slug": slug, "intelligence_index": score,
                    "aa_cost_per_task_intelligence_usd": cost,
                    "intelligence_source_url": AA_MODEL_URL.format(slug) if slug else None,
                    "intelligence_status": "ok" if cost is not None and cost > 0 else "missing_cost"})
    return out


def source_aa() -> tuple[dict, datetime, str]:
    errors = []
    for anchor in ANCHORS:
        url = AA_MODEL_URL.format(anchor)
        try:
            rows = records(parse_intelligence_rsc(fetch_text(url)))
        except Exception as exc:  # noqa: BLE001 — next anchor
            errors.append(f"{anchor}: {exc}"[:160])
            continue
        if len(rows) >= MIN_MODELS:
            return {"generated_at": now().isoformat(), "source_url": url, "data": rows}, now(), url
        errors.append(f"{anchor}: only {len(rows)} models")
    raise ValueError("AA intelligence: " + "; ".join(errors))

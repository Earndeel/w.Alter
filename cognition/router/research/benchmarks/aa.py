"""Artificial Analysis Intelligence Index and its cost per task, per model x reasoning level.

Since AA's redesign a model page only embeds the chart preview; the full catalogue is in its public page-data
manifest (research.benchmarks.aa_data). Two sources, no browser:
- the models leaderboard page (Next.js flight data, `initialModels`): every model x reasoning level with its
  Intelligence Index and its cost per AA task;
- the free Data API (`/api/v2/language/models/free`, paginated; key from walter-secrets, binding `aa_api_key` of host.json): the
  Intelligence Index as AA's documented contract. It wins over the page's score and scores a model the page lacks.
The index version (methodology page, "Version 5.0 October 2026 to current") is kept in the snapshot: a new version
re-bases every score, so `analysis.changes` only compares the board within one version.
History: parsing taken over from the aa-pareto-model-optimizer skill on 2026-10-21; leaderboard + API on 2026-10-28.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
from datetime import datetime
from typing import Any
from urllib.request import Request, urlopen

from walter_router import instance
from walter_router.research.web import MAX_BYTES, fetch_text, now

AA_MODEL_URL = "https://artificialanalysis.ai/models/{}"
# Model pages still read by research.benchmarks.aa_evaluations (several anchors in case one page is retired).
ANCHORS = ("gpt-6-luna", "gpt-5-6-luna", "claude-opus-5-5", "deepseek-v4-pro")
AA_LEADERBOARD_URL = "https://artificialanalysis.ai/leaderboards/models"
AA_API_URL = "https://artificialanalysis.ai/api/v2/language/models/free"
MAX_API_PAGES = 20
AA_METHODOLOGY_URL = "https://artificialanalysis.ai/methodology/intelligence-benchmarking"
# Index v5.0 scored 76 model x reasoning levels at launch (v4 had ~700): fewer priced rows means the page changed,
# keep the last good snapshot.
MIN_PRICED = 40
# Page and API disagree on more than this share of the models both score: the page is stale or misread.
MAX_DISAGREEMENT = 0.25
SCORE_TOLERANCE = 0.05

RSC_PUSH_PATTERN = re.compile(
    r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)'
)
VERSION_PATTERN = re.compile(r"Version (\d+(?:\.\d+)+) [A-Z][a-z]+ \d{4} to current")


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


def flight_text(page: str) -> str:
    """The page's whole flight stream, decoded (a row may span several pushes)."""
    return "".join(decode_rsc_string(m.group(1)) for m in RSC_PUSH_PATTERN.finditer(page))


def leaderboard_models(page: str) -> list[dict[str, Any]]:
    """The `initialModels` array of the leaderboard page: one object per model x reasoning level."""
    text = flight_text(page)
    found = re.search(r'"initialModels"\s*:\s*(?=\[)', text)
    if not found:
        raise RuntimeError("AA leaderboard: no initialModels array in the page")
    models, _ = json.JSONDecoder().raw_decode(text, found.end())
    return [m for m in models if isinstance(m, dict)]


def task_cost(value: Any) -> float | None:
    """Cost per AA task: a number on the leaderboard page, {'cost': {'total': …}} on the older model pages."""
    if isinstance(value, dict):
        value = (value.get("cost") or {}).get("total")
    return finite_number(value)


def records(raw_models: list[dict[str, Any]], api: dict[str, dict] | None = None) -> list[dict[str, Any]]:
    """One record per scored model x reasoning level; the API's score wins over the page's. Costs use the page's
    full precision, then the new API's published cost per task when the page has none; never estimate a cost."""
    api = api or {}
    out, seen = [], set()
    for model in raw_models:
        slug = str(model.get("slug") or "").strip() or None
        page_score = finite_number(model.get("intelligenceIndex"))
        score = api[slug]["score"] if slug in api else page_score
        if score is None:
            continue
        if not slug:
            raise ValueError("AA intelligence: scored model has no AA slug (partial leaderboard schema)")
        cost = task_cost(model.get("intelligenceIndexCostPerTask"))
        cost_source = "page" if cost is not None else None
        if cost is None and slug in api:
            cost = api[slug].get("cost")
            cost_source = "api" if cost is not None else None
        seen.add(slug)
        out.append({"name": model.get("shortName") or model.get("name") or slug, "slug": slug, "intelligence_index": score,
                    "score_source": "api" if slug in api else "page",
                    "aa_cost_per_task_intelligence_usd": cost,
                    "cost_source": cost_source,
                    "list_price_1m_input": finite_number(model.get("price1mInputTokens")),
                    "list_price_1m_output": finite_number(model.get("price1mOutputTokens")),
                    "estimated": bool(model.get("intelligenceIndexIsEstimated")),
                    "intelligence_source_url": AA_MODEL_URL.format(slug) if slug else None,
                    "intelligence_status": "ok" if cost is not None and cost > 0 else "missing_cost"})
    for slug, m in api.items():
        if slug not in seen:
            cost = m.get("cost")
            out.append({"name": m.get("name") or slug, "slug": slug, "intelligence_index": m["score"],
                        "score_source": "api", "aa_cost_per_task_intelligence_usd": cost,
                        "cost_source": "api" if cost is not None else None,
                        "list_price_1m_input": m.get("price_in"), "list_price_1m_output": m.get("price_out"), "estimated": False,
                        "intelligence_source_url": AA_MODEL_URL.format(slug),
                        "intelligence_status": "ok" if cost is not None and cost > 0 else "missing_cost"})
    return out


def api_key() -> str | None:
    """The instance's AA key, read from its vault through walter-secrets (host.json `aa_api_key`: item + field).
    Kept in this process only, never logged."""
    binding = instance.host().get("aa_api_key") or {}
    if not binding.get("item"):
        return None
    r = subprocess.run(["walter-secret", "get", binding["item"], binding.get("field", "api_key")],
                       capture_output=True, text=True, timeout=90)
    return (r.stdout.strip() or None) if r.returncode == 0 else None


def api_scores() -> tuple[dict[str, dict], str | None]:
    """{slug: {'score', 'name'}} from the free Data API, and an error label when it could not be read."""
    key = api_key()
    if not key:
        return {}, "no AA API key (host.json aa_api_key)"
    scores = {}
    try:
        for page in range(1, MAX_API_PAGES + 1):
            req = Request(f"{AA_API_URL}?page={page}",
                          headers={"x-api-key": key, "User-Agent": "Walter-Router/1.0", "Accept": "application/json"})
            with urlopen(req, timeout=60) as resp:  # noqa: S310 (fixed https host)
                raw = resp.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("AA API response too large")
            doc = json.loads(raw)
            data, pagination = doc["data"], doc["pagination"]
            if (not isinstance(data, list) or not isinstance(pagination, dict)
                    or pagination.get("page") != page or not isinstance(pagination.get("total_pages"), int)
                    or not page <= pagination["total_pages"] <= MAX_API_PAGES
                    or pagination.get("has_more") is not (page < pagination["total_pages"])):
                raise ValueError("AA API invalid pagination")
            for m in data:
                score = finite_number((m.get("evaluations") or {}).get("artificial_analysis_intelligence_index"))
                if m.get("slug") and score is not None:
                    cost = ((m.get("artificial_analysis_intelligence_index_cost") or {}).get("cost_per_task") or {})
                    pricing = m.get("pricing") or {}
                    scores[m["slug"]] = {"score": score, "name": m.get("name"),
                                         "cost": finite_number(cost.get("total_cost")),
                                         "price_in": finite_number(pricing.get("price_1m_input_tokens")),
                                         "price_out": finite_number(pricing.get("price_1m_output_tokens"))}
            if not pagination["has_more"]:
                return scores, None
    except Exception as exc:  # noqa: BLE001 — the key must never reach the message
        return {}, f"AA API: {type(exc).__name__} {getattr(exc, 'code', '')}".strip()
    return {}, "AA API: pagination limit reached"


def index_version() -> str | None:
    """The current Intelligence Index version from AA's methodology page; None when it cannot be read."""
    try:
        text = re.sub(r"<[^>]+>", " ", fetch_text(AA_METHODOLOGY_URL))
    except Exception:  # noqa: BLE001 — the version is a label, not a blocker
        return None
    found = VERSION_PATTERN.search(re.sub(r"\s+", " ", text))
    return found.group(1) if found else None


AA_INDEXES_URL = "https://artificialanalysis.ai/indexes"


def updates() -> dict[str, dict]:
    """AA's own map of recently changed evaluations ({slug: {'type': 'updated'|'new'|'underReview', 'description',
    'removeAfter'}}), carried by every page's layout; {} when it cannot be read."""
    try:
        page = fetch_text(AA_INDEXES_URL)
    except Exception:  # noqa: BLE001 — a label, not a blocker
        return {}
    from walter_router.research.benchmarks.aa_data import flight_values, objects
    badges = {}
    statuses = {"new", "updated", "underReview"}
    for value in flight_values(page):
        for obj in objects(value):
            # The change map no longer necessarily starts with the Intelligence Index (whose badge expires).
            for slug, change in obj.items():
                if slug != "change" and isinstance(change, dict) and change.get("type") in statuses:
                    badges[slug] = change
            change = obj.get("change")
            if obj.get("slug") and isinstance(change, dict) and change.get("type") in statuses:
                badges[obj["slug"]] = change
    return badges


def disagreement(raw_models: list[dict[str, Any]], scores: dict[str, dict]) -> dict[str, Any]:
    both = [(m["slug"], finite_number(m.get("intelligenceIndex")), scores[m["slug"]]["score"]) for m in raw_models
            if m.get("slug") in scores and finite_number(m.get("intelligenceIndex")) is not None]
    differ = [s for s, page, api in both if abs(page - api) > SCORE_TOLERANCE]
    return {"compared": len(both), "differ": len(differ), "examples": differ[:5]}


def source_aa() -> tuple[dict, datetime, str]:
    raw = leaderboard_models(fetch_text(AA_LEADERBOARD_URL))
    catalogue_url = None
    if any(not m.get("slug") for m in raw):
        # New leaderboard rows carry a release (base model) but no variant slug. The model catalogue supplies
        # exact variant identities and their own costs; never guess a slug from the display name or release.
        from walter_router.research.benchmarks.aa_data import model_catalogue
        raw, catalogue_url = model_catalogue()
    scores, api_error = api_scores()
    check = disagreement(raw, scores)
    if check["compared"] and check["differ"] / check["compared"] > MAX_DISAGREEMENT:
        raise ValueError(f"AA intelligence: page and API disagree on {check['differ']}/{check['compared']} models")
    rows = records(raw, scores)
    priced = sum(1 for r in rows if r["intelligence_status"] == "ok")
    if priced < MIN_PRICED:
        raise ValueError(f"AA intelligence: only {priced} models with a cost per task (page changed?)")
    version = index_version()
    doc = {"generated_at": now().isoformat(), "source_url": AA_LEADERBOARD_URL,
           "catalogue_url": catalogue_url, "index_version": version,
           "versions": {"aa_intelligence:intelligence": version} if version else {},
           "api": {"url": AA_API_URL, "models": len(scores), "error": api_error, "check": check}, "data": rows}
    return doc, now(), AA_LEADERBOARD_URL

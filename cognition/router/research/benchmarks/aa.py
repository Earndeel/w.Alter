"""Artificial Analysis Intelligence Index and its cost per task, per model x reasoning level.

Since AA's redesign of 2026-10-28 a model page no longer carries the whole catalogue (only the 28 chart models; the
rest moved to an encoded data file). Two reads, no browser:
- the models leaderboard page (Next.js flight data, `initialModels`): every model x reasoning level with its
  Intelligence Index and its cost per AA task — the free Data API does not publish the cost per task;
- the free Data API (`/api/v2/data/llms/models`, key from walter-secrets, binding `aa_api_key` of host.json): the
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
from walter_router.research.web import fetch_text, now

AA_MODEL_URL = "https://artificialanalysis.ai/models/{}"
# Model pages still read by research.benchmarks.aa_evaluations (several anchors in case one page is retired).
ANCHORS = ("gpt-6-luna", "gpt-5-6-luna", "claude-opus-5-5", "deepseek-v4-pro")
AA_LEADERBOARD_URL = "https://artificialanalysis.ai/leaderboards/models"
AA_API_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
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
    """One record per scored model x reasoning level; the API's score wins over the page's, and a model only the
    API scores is kept without a cost (it ranks on quality, it cannot enter a cost frontier)."""
    api = api or {}
    out, seen = [], set()
    for model in raw_models:
        slug = str(model.get("slug") or "").strip() or None
        page_score = finite_number(model.get("intelligenceIndex"))
        score = api[slug]["score"] if slug in api else page_score
        if score is None:
            continue
        cost = task_cost(model.get("intelligenceIndexCostPerTask"))
        seen.add(slug)
        out.append({"name": model.get("shortName") or model.get("name") or slug, "slug": slug, "intelligence_index": score,
                    "score_source": "api" if slug in api else "page",
                    "aa_cost_per_task_intelligence_usd": cost,
                    "list_price_1m_input": finite_number(model.get("price1mInputTokens")),
                    "list_price_1m_output": finite_number(model.get("price1mOutputTokens")),
                    "estimated": bool(model.get("intelligenceIndexIsEstimated")),
                    "intelligence_source_url": AA_MODEL_URL.format(slug) if slug else None,
                    "intelligence_status": "ok" if cost is not None and cost > 0 else "missing_cost"})
    for slug, m in api.items():
        if slug not in seen:
            out.append({"name": m.get("name") or slug, "slug": slug, "intelligence_index": m["score"],
                        "score_source": "api", "aa_cost_per_task_intelligence_usd": None,
                        "list_price_1m_input": None, "list_price_1m_output": None, "estimated": False,
                        "intelligence_source_url": AA_MODEL_URL.format(slug), "intelligence_status": "missing_cost"})
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
    req = Request(AA_API_URL, headers={"x-api-key": key, "User-Agent": "Walter-Router/1.0", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=60) as resp:  # noqa: S310 (fixed https host)
            data = json.loads(resp.read()).get("data") or []
    except Exception as exc:  # noqa: BLE001 — the key must never reach the message
        return {}, f"AA API: {type(exc).__name__} {getattr(exc, 'code', '')}".strip()
    scores = {}
    for m in data:
        score = finite_number((m.get("evaluations") or {}).get("artificial_analysis_intelligence_index"))
        if m.get("slug") and score is not None:
            scores[m["slug"]] = {"score": score, "name": m.get("name")}
    return scores, None


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
        text = flight_text(fetch_text(AA_INDEXES_URL))
    except Exception:  # noqa: BLE001 — a label, not a blocker
        return {}
    found = re.search(r'\{"artificial-analysis-intelligence-index":\{"type"', text)
    if not found:
        return {}
    try:
        badges, _ = json.JSONDecoder().raw_decode(text, found.start())
    except json.JSONDecodeError:
        return {}
    return {k: v for k, v in badges.items() if isinstance(v, dict)}


def disagreement(raw_models: list[dict[str, Any]], scores: dict[str, dict]) -> dict[str, Any]:
    both = [(m["slug"], finite_number(m.get("intelligenceIndex")), scores[m["slug"]]["score"]) for m in raw_models
            if m.get("slug") in scores and finite_number(m.get("intelligenceIndex")) is not None]
    differ = [s for s, page, api in both if abs(page - api) > SCORE_TOLERANCE]
    return {"compared": len(both), "differ": len(differ), "examples": differ[:5]}


def source_aa() -> tuple[dict, datetime, str]:
    raw = leaderboard_models(fetch_text(AA_LEADERBOARD_URL))
    scores, api_error = api_scores()
    check = disagreement(raw, scores)
    if check["compared"] and check["differ"] / check["compared"] > MAX_DISAGREEMENT:
        raise ValueError(f"AA intelligence: page and API disagree on {check['differ']}/{check['compared']} models")
    rows = records(raw, scores)
    priced = sum(1 for r in rows if r["intelligence_status"] == "ok")
    if priced < MIN_PRICED:
        raise ValueError(f"AA intelligence: only {priced} models with a cost per task (page changed?)")
    version = index_version()
    doc = {"generated_at": now().isoformat(), "source_url": AA_LEADERBOARD_URL, "index_version": version,
           "versions": {"aa_intelligence:intelligence": version} if version else {},
           "api": {"models": len(scores), "error": api_error, "check": check}, "data": rows}
    return doc, now(), AA_LEADERBOARD_URL

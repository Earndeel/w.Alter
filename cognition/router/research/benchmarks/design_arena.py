"""Design Arena (designarena.ai) human-preference leaderboards: models arena per design category (website, UI
component, game, dataviz, 3D, SVG, graphic design, logo, overall) and agents arena (full-stack, web, mobile, native
apps…), through its public JSON API. Collector taken over from the aa-pareto-model-optimizer skill on 2026-10-21
(same document shape)."""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any
from urllib.request import Request, urlopen

from walter_router.research.web import MAX_BYTES, now, post_json

DA_BASE = "https://www.designarena.ai"
LEADERBOARD_API = DA_BASE + "/api/leaderboard"
REGISTRY_API = DA_BASE + "/api/registry"
CATEGORIES = ["allcategories", "website", "uicomponent", "gamedev", "dataviz", "3d", "svg", "graphicdesign", "logo"]
AGENT_CATEGORIES = ["fullstack", "agon_webapps", "mobileapps", "nativeapps", "agentic_3d", "agon_dataviz", "agon_html"]
PAUSE_S = 0.5   # crowdsourced API: one call at a time


def normalize_slug(model_id: str) -> str:
    """Design Arena ids use dots (gpt-5.6-sol), AA slugs hyphens: lowercase, dots/underscores -> hyphens."""
    return (model_id or "").lower().replace(".", "-").replace("_", "-").strip()


def leaderboard(category: str, arena_type: str = "models") -> tuple[list[dict[str, Any]], dict]:
    body = post_json(LEADERBOARD_API, {"arenaType": arena_type, "category": category, "variationName": "public"})
    rows = [{"model": r.get("modelId"), "slug_norm": normalize_slug(r.get("modelId", "")), "elo": r.get("elo"),
             "win_rate": r.get("winRate"), "battles": r.get("battles"), "wins": r.get("wins"), "losses": r.get("losses"),
             "bt_stderr": r.get("btStdErr"), "avg_generation_time_ms": r.get("avgGenerationTimeMs"),
             "category": category, "arena_type": arena_type} for r in body.get("data") or []]
    return rows, body.get("metadata") or {}


def registry() -> dict[str, dict[str, Any]]:
    req = Request(REGISTRY_API, headers={"User-Agent": "Mozilla/5.0 (Walter-Router/1.0)", "Accept": "application/json"})
    with urlopen(req, timeout=60) as resp:  # noqa: S310 (fixed https URL)
        models = json.loads(resp.read(MAX_BYTES)).get("models", {})
    return {normalize_slug(mid): {"model_id": mid, "display_name": m.get("displayName"), "provider": m.get("provider"),
                                  "active": m.get("active"), "open_source": m.get("openSource"), "router": m.get("router"),
                                  "arenas": m.get("arenas"), "input_modalities": m.get("inputModalities")}
            for mid, m in models.items()}


def source_da(parts: set[str] | None = None) -> tuple[dict, datetime, str]:
    """Every category, or only `parts` (category keys; 'agents' = the agents arena)."""
    reg = registry()
    categories: dict[str, Any] = {}
    meta: dict = {}
    for cat in [c for c in CATEGORIES if not parts or c in parts]:
        categories[cat], m = leaderboard(cat)
        meta = m if cat == "allcategories" else meta
        time.sleep(PAUSE_S)
    for cat in (AGENT_CATEGORIES if not parts or "agents" in parts else []):
        try:
            rows, _ = leaderboard(cat, "agents")
        except RuntimeError:
            continue
        if rows:
            categories[f"agents/{cat}"] = rows
        time.sleep(PAUSE_S)
    if not parts and len(categories.get("allcategories") or []) < 50:
        raise ValueError("Design Arena: overall leaderboard nearly empty")
    doc = {"generated_at": now().isoformat(), "source": "Design Arena", "source_url": DA_BASE + "/leaderboard",
           "metadata": {"total_votes": meta.get("totalVotes"), "last_update_time": meta.get("lastUpdateTime")},
           "categories": categories,
           "agent_categories": {k[len("agents/"):]: v for k, v in categories.items() if k.startswith("agents/")},
           "registry": reg}
    return doc, now(), doc["source_url"]

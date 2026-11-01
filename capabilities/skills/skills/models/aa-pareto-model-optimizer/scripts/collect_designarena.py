#!/usr/bin/env python3
"""Collect Design Arena (https://designarena.ai) human-preference leaderboards.

Design Arena is a crowdsourced benchmark where real users judge single-file HTML
outputs (website, UI component, game, data-viz, 3D, ...). Its Elo ratings capture
human preference that synthetic benchmarks (AA Intelligence/Agentic Index) miss.

This collector is deterministic and makes no LLM call. It writes
``$HERMES_HOME/cache/aa-pareto/designarena.json`` (or ``--output-dir``) with:

- ``generated_at`` and registry metadata (total votes, last update);
- ``categories``: Elo leaderboard rows per Design Arena category
  (allcategories = overall, website, uicomponent, gamedev, dataviz, 3d, ...);
- per-row ``model`` helpers derived from the /api/registry display names.

The output is designed to join the AA Pareto snapshot by ``slug``: Design Arena
``modelId`` values use dots (``gpt-5.6-sol``) whereas AA slugs use hyphens, so a
normalized match is provided (see ``slug_norm``).

Dependencies: requests.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit("requests is required for the Design Arena collector") from exc

DA_BASE = "https://www.designarena.ai"
LEADERBOARD_API = DA_BASE + "/api/leaderboard"
REGISTRY_API = DA_BASE + "/api/registry"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)

# Design Arena models-arena categories worth collecting for design/human-preference.
# Note: "Image to Website" / "Video to Website" are the `website` category with
# inputModality=image/video, not separate leaderboard categories.
DEFAULT_CATEGORIES = [
    "allcategories",  # overall composite
    "website",
    "uicomponent",
    "gamedev",
    "dataviz",
    "3d",
    "svg",
    "graphicdesign",
    "logo",
]

# Agentic-build categories (arenaType="agents"): real-work build competence
# (full-stack React apps, web apps, mobile apps, agentic 3D / data-viz / HTML).
# Empty categories (0 rows) are skipped quietly by the collector.
DEFAULT_AGENT_CATEGORIES = [
    "fullstack",
    "agon_webapps",
    "mobileapps",
    "nativeapps",
    "agentic_3d",
    "agon_dataviz",
    "agon_html",
]


def hermes_home() -> Path:
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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_slug(model_id: str) -> str:
    """Map a Design Arena modelId to the AA-style hyphen slug for joining.

    DA uses ``gpt-5.6-sol``; AA uses ``gpt-5-6-sol``. Lowercase, dots -> hyphens,
    underscores -> hyphens, trim. Tail date suffixes like ``-0731`` are left in
    place so the caller decides (they may match AA date-stamped slugs).
    """
    return (model_id or "").lower().replace(".", "-").replace("_", "-").strip()


def request_json(session: Any, url: str, *,
                 method: str = "GET", payload: dict | None = None,
                 attempts: int = 4) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            if method == "POST":
                resp = session.post(url, json=payload, timeout=60)
            else:
                resp = session.get(url, timeout=60)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise RuntimeError(f"HTTP {resp.status_code} from {url}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # requests exceptions vary across versions
            body = b""
            try:
                last_error = exc
            except Exception:
                pass
            if attempt + 1 < attempts:
                # polite backoff: 429/5xx and transient 400s (rate limiting) recover
                time.sleep(1 + 2 ** attempt)
    raise RuntimeError(f"Unable to fetch {url}: {last_error}") from last_error


def collect_leaderboard(session: Any, category: str, *,
                        arena_type: str = "models") -> list[dict[str, Any]]:
    payload = {
        "arenaType": arena_type,
        "category": category,
        "variationName": "public",
    }
    body = request_json(session, LEADERBOARD_API, method="POST", payload=payload)
    rows = body.get("data", []) or []
    out = []
    for row in rows:
        out.append({
            "model": row.get("modelId"),
            "slug_norm": normalize_slug(row.get("modelId", "")),
            "elo": row.get("elo"),
            "win_rate": row.get("winRate"),
            "battles": row.get("battles"),
            "wins": row.get("wins"),
            "losses": row.get("losses"),
            "bt_stderr": row.get("btStdErr"),
            "avg_generation_time_ms": row.get("avgGenerationTimeMs"),
            "category": category,
            "arena_type": arena_type,
        })
    return out


def collect_registry(session: Any) -> dict[str, dict[str, Any]]:
    body = request_json(session, REGISTRY_API)
    models = body.get("models", {})
    out: dict[str, dict[str, Any]] = {}
    for mid, meta in models.items():
        out[normalize_slug(mid)] = {
            "model_id": mid,
            "display_name": meta.get("displayName"),
            "provider": meta.get("provider"),
            "active": meta.get("active"),
            "open_source": meta.get("openSource"),
            "router": meta.get("router"),
            "arenas": meta.get("arenas"),
            "input_modalities": meta.get("inputModalities"),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write designarena.json (default: HERMES_HOME/cache/aa-pareto)",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        default=DEFAULT_CATEGORIES,
        help="Design Arena models categories to collect (default: overall + design set)",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    output_dir = args.output_dir or default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    registry = collect_registry(session)
    categories: dict[str, Any] = {}

    for cat in args.categories:
        rows = collect_leaderboard(session, cat, arena_type="models")
        categories[cat] = rows
        if not args.quiet:
            print(f"  collected models/{cat}: {len(rows)} rows")
        time.sleep(0.5)  # be gentle with the crowdsourced API
    for cat in DEFAULT_AGENT_CATEGORIES:
        try:
            rows = collect_leaderboard(session, cat, arena_type="agents")
        except RuntimeError as exc:
            if not args.quiet:
                print(f"  skipped agents/{cat}: {exc}")
            continue
        if not rows:
            if not args.quiet:
                print(f"  skipped agents/{cat}: no published rows")
            continue
        categories[f"agents/{cat}"] = rows
        if not args.quiet:
            print(f"  collected agents/{cat}: {len(rows)} rows")
        time.sleep(0.5)

    # Fetch allcategories metadata for vote/update info (idempotent re-fetch is fine).
    meta_body = request_json(
        session, LEADERBOARD_API, method="POST",
        payload={"arenaType": "models", "category": "allcategories", "variationName": "public"},
    )
    metadata = meta_body.get("metadata") or {}
    votes_total = metadata.get("totalVotes")
    last_update = metadata.get("lastUpdateTime")

    doc = {
        "generated_at": now_iso(),
        "source": "Design Arena",
        "source_url": "https://www.designarena.ai/leaderboard",
        "metadata": {
            "total_votes": votes_total,
            "last_update_time": last_update,
        },
        "categories": categories,
        "agent_categories": {k[len("agents/"):]: v for k, v in categories.items() if k.startswith("agents/")},
        "registry": registry,
    }

    out_path = output_dir / "designarena.json"
    out_path.write_text(json.dumps(doc, indent=1))
    counts = {k: len(v) for k, v in categories.items()}
    if not args.quiet:
        total = sum(counts.values())
        print(
            f"Design Arena collected: {total} rows across {len(categories)} categories "
            f"(registry {len(registry)} models) -> {out_path}"
        )
        print("  per-category:", counts)


if __name__ == "__main__":
    main()

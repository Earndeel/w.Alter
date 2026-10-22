"""The hosts behind OpenRouter for each model of the active library: price, compression (quantization), reliability
(uptime 30 min / 24 h), speed and tool support — one model can cost 4x more on one host than on another, or be served
4-bit compressed. Read from openrouter.ai/api/v1/models/<id>/endpoints (public, no key) for the models the router uses
(models.shortlist + pinned favourites + the text tiers), not the whole catalogue."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from walter_router.research.web import fetch_json, now

ENDPOINTS_URL = "https://openrouter.ai/api/v1/models/{}/endpoints"
PAUSE_S = 0.15


def watched(conn) -> dict[str, str]:
    """router model_id -> OpenRouter id, for every model the active library uses or proposes."""
    rows = conn.execute("""
        with used as (select model_id from models.shortlist
                      union select pinned_model_id from models.preferences where pinned_model_id is not null)
        select distinct on (o.model_id) o.model_id, split_part(o.offer_key, ' | ', 1) as or_id
        from models.offers o join used using (model_id)
        where o.provider = 'openrouter' and o.interface = 'chat'
          and o.snapshot_id = (select snapshot_id from models.latest_snapshots where kind = 'openrouter')
        order by o.model_id, o.offer_key""").fetchall()
    return {r["model_id"]: r["or_id"] for r in rows}


def source_or_endpoints() -> tuple[dict, datetime, str]:
    from walter_router.store import db   # research reads the store only to know which models to look at
    with db.connect() as conn:
        models = watched(conn)
    out: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for mid, or_id in sorted(models.items()):
        try:
            data = fetch_json(ENDPOINTS_URL.format(or_id))["data"]
            out[or_id] = {"model_id": mid, "endpoints": data.get("endpoints") or []}
        except Exception as exc:  # noqa: BLE001 — one model must not lose the others
            errors[or_id] = f"{type(exc).__name__}: {exc}"[:160]
        time.sleep(PAUSE_S)
    if models and not out:
        raise ValueError(f"OpenRouter endpoints: nothing read ({list(errors.items())[:3]})")
    return {"models": out, "errors": errors}, now(), "https://openrouter.ai/api/v1/models/{id}/endpoints"

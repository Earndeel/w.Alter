"""Compute ranked candidates per task from the latest snapshots, on the cheapest *real* price.

The Pareto mathematics is the aa-pareto-model-optimizer skill's own code (make_frontier, ladder_knee), so the
router and the skill can never disagree on what the frontier is.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

from . import collect, media

SKILL = Path(os.environ.get("HERMES_HOME", "/root/.hermes")) / "skills/research/aa-pareto-model-optimizer/scripts"
DEFAULT_EFFORTS = ("medium", "high")  # assumed effort when a leaderboard lists a model without one (flagged)
MEDIA_UNITS = {"image": "per image", "video": "per second", "audio": "per 1000 characters", "music": None}
BENCH_KIND = {"aa_intelligence": "aa", "aa_mm": "mm", "da_models": "da", "da_agents": "da", "arena": "arena"}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"aa_skill_{name}", SKILL / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PARETO = _load("refresh")
LADDER = _load("router")


def latest_snapshots(conn) -> dict[str, int]:
    return {r["kind"]: r["snapshot_id"] for r in conn.execute(
        "select distinct on (kind) kind, snapshot_id from models.snapshots order by kind, fetched_at desc, snapshot_id desc")}


def load_offers(conn, snaps: dict[str, int]) -> dict[str, list[dict]]:
    ids = [snaps[k] for k in collect.OFFER_KINDS if k in snaps]
    by_model: dict[str, list[dict]] = {}
    for r in conn.execute("select * from models.offers where snapshot_id = any(%s)", (ids,)):
        by_model.setdefault(r["model_id"], []).append(r)
    return by_model


def blended(offer: dict) -> float | None:
    """AA's blended token price: 3 parts input, 1 part output."""
    if offer["price_in_1m"] is None or offer["price_out_1m"] is None:
        return None
    return (3 * offer["price_in_1m"] + offer["price_out_1m"]) / 4


def chat_route(offers: list[dict], list_cost: float | None) -> dict[str, Any]:
    """Cheapest paid route for a chat model, scaling AA's list-price task cost by the provider/list price ratio.

    The OpenRouter price is the list reference (it mirrors first-party pricing). A provider without a reference
    is kept unscaled (conservative) and flagged.
    """
    chat = [o for o in offers if o["interface"] == "chat"]
    subscription = next((o["provider"] for o in chat if o["access"] == "subscription"), None)
    ref = next((blended(o) for o in chat if o["provider"] == "openrouter" and blended(o)), None)
    best = None
    for o in chat:
        if o["access"] != "paid" or blended(o) is None:
            continue
        ratio, basis = (blended(o) / ref, "scaled_vs_openrouter_list") if ref else (1.0, "unscaled_no_list_reference")
        cost = list_cost * ratio if list_cost is not None else None
        cand = {"provider": o["provider"], "offer_key": o["offer_key"], "ratio": ratio, "basis": basis, "cost": cost,
                "blended_1m": blended(o)}
        if best is None or (cand["cost"] is not None and (best["cost"] is None or cand["cost"] < best["cost"])) \
                or (cand["cost"] is None and best["cost"] is None and cand["blended_1m"] < best["blended_1m"]):
            best = cand
    return {"paid": best, "subscription": subscription, "callable": bool(best or subscription)}


def _fields(o: dict) -> dict:
    """Stored classification of an offer (models.offers columns), or computed from its key when absent."""
    if "offer_kind" in o:
        return {k: o[k] for k in ("offer_kind", "modes", "resolution", "norm_price", "norm_unit")}
    c = media.classify(o["interface"], o["offer_key"])
    price, unit = media.norm_price(o["interface"], o["unit_price"], o["unit"], o["offer_key"])
    return {"offer_kind": c["kind"], "modes": c["modes"], "resolution": c["resolution"],
            "norm_price": price if c["kind"] == "generation" else None, "norm_unit": unit}


def media_route(offers: list[dict], interface: str, modes: list[str] | None = None) -> dict[str, Any]:
    """Cheapest generation offer in the interface's comparable unit (video per second, image per image), restricted
    to the task's generation modes; input fees, upscales, extensions and free auxiliary SKUs never count."""
    want = MEDIA_UNITS.get(interface)
    paid = []
    for o in offers:
        if o["interface"] != interface:
            continue
        f = _fields(o)
        if f["offer_kind"] != "generation" or f["norm_price"] is None or not media.compatible(f["modes"], modes):
            continue
        if want and f["norm_unit"] != want:
            continue
        paid.append({**o, **f})
    by_res: dict[str, dict] = {}
    for c in paid:
        res = c["resolution"] or "any"
        if res not in by_res or c["norm_price"] < by_res[res]["cost"]:
            by_res[res] = {"provider": c["provider"], "offer_key": c["offer_key"], "cost": c["norm_price"]}
    any_offer = [o for o in offers if o["interface"] == interface]
    best = min(paid, key=lambda o: o["norm_price"], default=None)
    top = max(paid, key=lambda o: o["norm_price"], default=None)
    route = None
    if best:
        route = {"provider": best["provider"], "offer_key": best["offer_key"], "cost": best["norm_price"],
                 "unit": best["norm_unit"], "max_variant_cost": top["norm_price"], "max_variant": top["offer_key"],
                 "by_resolution": by_res}
    elif any_offer:
        o = any_offer[0]
        route = {"provider": o["provider"], "offer_key": o["offer_key"], "cost": None, "unit": None}
    ui = next((o["provider"] for o in any_offer if o["access"] == "ui"), None)
    return {"paid": route, "subscription": None, "ui": ui, "callable": bool(any_offer)}


def _intelligence_index(conn, snaps: dict[str, int], offers: dict[str, list[dict]]) -> dict[tuple[str, str], dict]:
    rows = {}
    if "aa" not in snaps:
        return rows
    for b in conn.execute("""select * from models.benchmarks where snapshot_id = %s and benchmark = 'aa_intelligence'""",
                          (snaps["aa"],)):
        route = chat_route(offers.get(b["model_id"], []), b["cost"])
        rows[(b["model_id"], b["variant"])] = {**b, "route": route}
    return rows


def _row(task: str, level: str, rank: int, cand: dict, **extra) -> dict:
    route = cand["route"]
    paid = route.get("paid") or {}
    return dict(task=task, level=level, rank=rank, model_id=cand["model_id"], variant=cand["variant"],
                display_name=cand["display_name"], quality=cand["score"], quality_unit=cand["score_unit"],
                real_cost=cand.get("real_cost"), cost_unit=cand.get("real_cost_unit"),
                provider=paid.get("provider"), offer_key=paid.get("offer_key"), subscription=route.get("subscription"),
                reasons={**{k: v for k, v in paid.items() if k not in ("provider", "offer_key")}, **extra})


def _ladder(cands: list[dict], minimum_score: float, cost_cap: float) -> dict | None:
    rows = [{"name": c["display_name"], "slug": f'{c["model_id"]}|{c["variant"]}', "score": c["score"],
             "cost": c["real_cost"], "_c": c} for c in cands if c.get("real_cost") and c["real_cost"] > 0]
    if len(rows) < 2:
        return None
    frontier = PARETO.make_frontier(rows, "score", "cost", minimum_score, 0.5, 0.5, 10.0, 2.0, cost_cap)
    by_slug = {r["slug"]: r["_c"] for r in rows}
    ladder = frontier["upgrade_ladder"]
    if not ladder["tiers"]:
        return None
    knee = LADDER.ladder_knee(ladder["tiers"])
    return {"anchor": by_slug[ladder["tiers"][0]["slug"]], "knee": by_slug[knee["slug"]],
            "ceiling": by_slug[(ladder.get("quality_ceiling") or ladder["tiers"][-1])["slug"]],
            "frontier": [by_slug[r["slug"]] for r in frontier["pragmatic_frontier"]]}


def compute(conn) -> list[dict]:
    snaps = latest_snapshots(conn)
    offers = load_offers(conn, snaps)
    intel = _intelligence_index(conn, snaps, offers)
    tasks = list(conn.execute("select * from models.tasks where quality_benchmark is not null"))
    out: list[dict] = []
    for t in tasks:
        kind = BENCH_KIND[t["quality_benchmark"]]
        if kind not in snaps:
            continue
        bench = list(conn.execute("""select * from models.benchmarks where snapshot_id = %s and benchmark = %s and task = %s""",
                                  (snaps[kind], t["quality_benchmark"], t["quality_task"])))
        cands = []
        for b in bench:
            mo = offers.get(b["model_id"], [])
            if t["interface"] == "chat":
                ref = intel.get((b["model_id"], b["variant"]))
                assumed = None
                if ref is None and not b["variant"]:
                    for eff in DEFAULT_EFFORTS:
                        if (b["model_id"], eff) in intel:
                            ref, assumed = intel[(b["model_id"], eff)], eff
                            break
                list_cost = b["cost"] if b["benchmark"] == "aa_intelligence" else (ref["cost"] if ref else None)
                route = chat_route(mo, list_cost)
                cost_unit = "usd_per_aa_task" if list_cost is not None else None
                if assumed:
                    route = {**route, "paid": {**(route["paid"] or {}), "cost_basis_effort_assumed": assumed}}
            else:
                route = media_route(mo, t["interface"], t["modes"])
                cost_unit = (route["paid"] or {}).get("unit")
            if not route["callable"]:
                continue
            cands.append({**b, "route": route, "real_cost": (route["paid"] or {}).get("cost"), "real_cost_unit": cost_unit})
        if not cands:
            continue
        best = sorted(cands, key=lambda c: (-c["score"], c["real_cost"] if c["real_cost"] is not None else float("inf")))
        from .knowledge import tie_break  # late import: knowledge -> choose -> select
        ranked = tie_break(conn, t["task"], [_row(t["task"], "best", i + 1, c) for i, c in enumerate(best[:6])])
        out += [{**r, "rank": i + 1} for i, r in enumerate(ranked[:5])]
        if t["task"] == "general":
            lad = _ladder(cands, 35.0, 0.75)
            if lad:
                out.append(_row("general", "L1", 1, lad["anchor"], role="value_anchor"))
                out.append(_row("general", "L2", 1, lad["knee"], role="ladder_knee"))
                out.append(_row("general", "L3", 1, lad["ceiling"], role="quality_ceiling"))
                out += [_row("general", "frontier", i + 1, c) for i, c in enumerate(lad["frontier"])]
        else:
            lad = _ladder(cands, 0.0, float("inf"))
            if lad:
                out.append(_row(t["task"], "value", 1, lad["knee"], role="ladder_knee"))
                out += [_row(t["task"], "frontier", i + 1, c) for i, c in enumerate(lad["frontier"])]
    return out


def save(conn, run_id: int, rows: list[dict]) -> None:
    for r in rows:
        conn.execute("""insert into models.selection (run_id, task, level, rank, model_id, variant, display_name, quality,
                        quality_unit, real_cost, cost_unit, provider, offer_key, subscription, reasons)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                     (run_id, r["task"], r["level"], r["rank"], r["model_id"], r["variant"], r["display_name"], r["quality"],
                      r["quality_unit"], r["real_cost"], r["cost_unit"], r["provider"], r["offer_key"], r["subscription"],
                      json.dumps(r["reasons"], default=str)))

"""Compute ranked candidates per task from the latest snapshots, on the cheapest *real* price.

The Pareto mathematics is the aa-pareto-model-optimizer skill's own code (make_frontier, ladder_knee), so the
router and the skill can never disagree on what the frontier is.
"""
from __future__ import annotations

import re

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

from . import collect, media
from . import instance

SKILL = instance.hermes_home() / "skills/research/aa-pareto-model-optimizer/scripts"
DEFAULT_EFFORTS = ("medium", "high")  # assumed effort when a leaderboard lists a model without one (flagged)
MEDIA_UNITS = media.NORM_UNITS   # image per image, video per second, voice per 1000 characters, stt per minute…
BENCH_KIND = {"aa_intelligence": "aa", "aa_decision": "aa_decision", "aa_mm": "mm", "da_models": "da", "da_agents": "da", "arena": "arena",
              "bridgebench": "bridgebench", "aa_stt": "aa_stt", "agentset": "agentset", "mteb": "mteb"}


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


BOARD_GRACE_DAYS = 21


def board_snapshot(conn, snaps: dict[str, int], benchmark: str, bench_task: str) -> int | None:
    """Snapshot to read one board from: the latest of its source, or — when the board is empty there (page changed,
    blocked) — the last snapshot that had it, within BOARD_GRACE_DAYS (the router keeps the last known ranking; a
    'board_down' alert tells the owner)."""
    kind = BENCH_KIND.get(benchmark)
    sid = snaps.get(kind)
    if sid is None:
        return None
    if conn.execute("select 1 from models.benchmarks where snapshot_id = %s and benchmark = %s and task = %s limit 1",
                    (sid, benchmark, bench_task)).fetchone():
        return sid
    row = conn.execute("""select s.snapshot_id from models.snapshots s where s.kind = %s
                          and s.fetched_at > now() - make_interval(days => %s)
                          and exists (select 1 from models.benchmarks x where x.snapshot_id = s.snapshot_id
                                      and x.benchmark = %s and x.task = %s)
                          order by s.fetched_at desc limit 1""", (kind, BOARD_GRACE_DAYS, benchmark, bench_task)).fetchone()
    return row["snapshot_id"] if row else sid


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


def decision_route(offers: list[dict], modes: list[str] | None = None) -> dict[str, Any]:
    """Cheapest Decisions-API offer (decision models are billed on input tokens only) that reads every input the
    task needs besides text (e.g. 'image' for the vision decision task)."""
    need = set(modes or [])
    paid = [o for o in offers if o["interface"] == "decisions" and o.get("price_in_1m") is not None
            and need <= set(o.get("modes") or [])]
    best = min(paid, key=lambda o: o["price_in_1m"], default=None)
    route = {"provider": best["provider"], "offer_key": best["offer_key"], "cost": best["price_in_1m"],
             "unit": "usd_per_1m_input_tokens"} if best else None
    return {"callable": bool(best), "paid": route, "subscription": None}


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


def _tier_rows(cands: list[dict]) -> list[dict]:
    """The owner's three text tiers (tiers.py) on the AA frontier of callable model x reasoning level, real costs."""
    from . import tiers  # late import keeps the module graph flat
    pts = [{**c, "cost": c["real_cost"]} for c in cands if c.get("real_cost")]
    t = tiers.compute(pts)
    rows = []
    for level, why in (("L1", "économique : premier coude au-dessus du plancher de qualité"),
                       ("L2", "intermédiaire : meilleur gain en points par $ depuis L1"),
                       ("L3", "haut de gamme : meilleur gain depuis L2 dans la bande du plafond")):
        if t[level]:
            p = t[level]
            rows.append(_row("general", level, 1, p, role=why, marginal=p.get("marginal"), method=t.get("params")))
    rows += [_row("general", "frontier", i + 1, p, marginal=p.get("marginal"))
             for i, p in enumerate(q for q in t["frontier"] if q["score"] >= tiers.QUALITY_FLOOR - 5)]
    return rows


def _best_by_composite(conn, t: dict, snaps: dict, offers: dict, cands: list[dict], n: int = 6) -> list[dict]:
    """'best' level: callable models ordered by the weighted multi-board score (scoring.composite)."""
    from .scoring import composite  # late import (scoring -> select)
    primary = {}
    for c in cands:  # the primary board's best variant keeps its route and real cost (AA cost per task for chat)
        if c["model_id"] not in primary or c["score"] > primary[c["model_id"]]["score"]:
            primary[c["model_id"]] = c
    rows = []
    for comp in composite(conn, t["task"], snaps):
        mid = comp["model_id"]
        if mid in primary:
            route, cost, unit, variant = primary[mid]["route"], primary[mid]["real_cost"], \
                primary[mid]["real_cost_unit"], primary[mid]["variant"]
        else:
            mo = offers.get(mid, [])
            route = chat_route(mo, None) if t["interface"] == "chat" else decision_route(mo, t["modes"]) \
                if t["interface"] == "decisions" else media_route(mo, t["interface"], t["modes"])
            if not route["callable"]:
                continue
            cost, variant = (route["paid"] or {}).get("cost"), ""
            unit = (route["paid"] or {}).get("unit") if t["interface"] != "chat" else None
        paid = route.get("paid") or {}
        name = conn.execute("select coalesce(display_name, model_id) as n from models.canonical where model_id = %s",
                            (mid,)).fetchone()["n"]
        rows.append(dict(task=t["task"], level="best", rank=len(rows) + 1, model_id=mid, variant=variant,
                         display_name=name, quality=comp["composite"], quality_unit="Composite /100",
                         real_cost=cost, cost_unit=unit, provider=paid.get("provider"), offer_key=paid.get("offer_key"),
                         subscription=route.get("subscription"),
                         reasons={**{k: v for k, v in paid.items() if k not in ("provider", "offer_key")},
                                  "boards": comp["boards"], "evidence_weight": comp["evidence_weight"]}))
        if len(rows) >= n:
            break
    return rows


MEDIA_EXEC_INTERFACES = ("image", "video", "audio", "music")
_VERSION = re.compile(r"^(.*?)-(\d+(?:-\d+)*)(?:-(.*))?$")


def family(model_id: str) -> tuple[str, tuple, str] | None:
    """'gpt-image-2-5-sunburst' -> ('gpt-image', (2, 5), 'sunburst'); 'gpt-image-2' -> ('gpt-image', (2,), '')."""
    m = _VERSION.match(model_id)
    if not m:
        return None
    return m.group(1), tuple(int(x) for x in m.group(2).split("-")), m.group(3) or ""


LEVEL_WORDS = {"minimal", "low", "medium", "high", "xhigh", "max", "preview", "latest"}


def same_line(model_id: str, newer_id: str) -> bool:
    """newer_id is a later version of the SAME product line: same prefix, higher version, and it keeps every product
    word of the old suffix (reasoning levels aside). 'gpt-image-2' -> 'gpt-image-2-5-sunburst' yes;
    'gemini-3-1-flash-live-high' -> 'gemini-3-8-flash-tts' no (a TTS model is not a newer Live model; 2026-10-18
    refresh failure)."""
    a, b = family(model_id), family(newer_id)
    if not a or not b or a[0] != b[0] or b[1] <= a[1]:
        return False
    words = lambda suffix: {w for w in suffix.split("-") if w and w not in LEVEL_WORDS}
    return words(a[2]) <= words(b[2])


def _executable_first(conn, t: dict, ranked: list[dict], offers: dict) -> list[dict]:
    """The owner (2026-10-14, logo): the best measured model must be one Walter can run; and when a newer version of
    it exists, runs and is not benchmarked on this task yet, it goes first with a warning (GPT Image 2 measured on
    the logo board, GPT Image 2.5 Sunburst not yet: Sunburst, « version supérieure pas encore classée »)."""
    from .media_exec import _models   # late import (media_exec -> select)
    runnable = {m for m, c in _models().items() if c.get("kind") in ("image", "video", "audio", "music")}
    pinned = {r["pinned_model_id"] for r in conn.execute("select pinned_model_id from models.preferences "
                                                         "where pinned_model_id is not null")}
    # 'measured' = on the task's own board (DA logo for logo), not only on a generic board it borrows weight from
    sid = board_snapshot(conn, latest_snapshots(conn), t["quality_benchmark"], t["quality_task"])
    measured = {r["model_id"] for r in conn.execute(
        "select distinct model_id from models.benchmarks where snapshot_id = %s and benchmark = %s and task = %s",
        (sid, t["quality_benchmark"], t["quality_task"]))} if sid else {r["model_id"] for r in ranked}
    top_measured = [r for r in ranked if r["model_id"] in measured]
    out = []
    if top_measured:
        top, fam = top_measured[0], family(top_measured[0]["model_id"])
        newer = [m for m in runnable if m not in measured and fam and same_line(top["model_id"], m)
                 and any(o["interface"] == t["interface"] for o in offers.get(m, []))]
        newer.sort(key=lambda m: (m in pinned, family(m)[1]), reverse=True)
        if newer:
            name = conn.execute("select coalesce(display_name, model_id) as n from models.canonical where model_id = %s",
                                (newer[0],)).fetchone()
            route = media_route(offers.get(newer[0], []), t["interface"], t["modes"])
            paid = route.get("paid") or {}
            out.append({**top, "model_id": newer[0], "variant": "", "display_name": name["n"] if name else newer[0],
                        "quality": None, "real_cost": paid.get("cost"), "cost_unit": paid.get("unit"),
                        "provider": paid.get("provider"), "offer_key": paid.get("offer_key"),
                        "reasons": {"warning": f"version supérieure de {top['display_name']}, pas encore classée sur "
                                               f"ce benchmark", "successor_of": top["model_id"],
                                    "measured_quality": top["quality"]}})
    out += [r for r in ranked if r["model_id"] in runnable and r["model_id"] not in {o["model_id"] for o in out}]
    if not out:
        return ranked   # nothing runnable: keep the measurement (the library shows « pas d'exécuteur »)
    return out


def general_points(conn) -> list[dict]:
    """Every callable model x reasoning level on the AA Intelligence Index with its real cost per AA task (the cloud
    behind the L1/L2/L3 method) — for the library page's Pareto chart."""
    snaps = latest_snapshots(conn)
    offers = load_offers(conn, snaps)
    if "aa" not in snaps:
        return []
    out = []
    for b in conn.execute("""select model_id, variant, display_name, score, cost from models.benchmarks
                             where snapshot_id = %s and benchmark = 'aa_intelligence'""", (snaps["aa"],)):
        route = chat_route(offers.get(b["model_id"], []), b["cost"])
        cost = (route.get("paid") or {}).get("cost")
        if route["callable"] and cost:
            out.append({"model_id": b["model_id"], "variant": b["variant"], "name": b["display_name"],
                        "score": b["score"], "cost": cost, "cost_aa": b["cost"],
                        "provider": (route.get("paid") or {}).get("provider"),
                        "subscription": bool(route.get("subscription"))})
    return out


def compute(conn) -> list[dict]:
    snaps = latest_snapshots(conn)
    offers = load_offers(conn, snaps)
    intel = _intelligence_index(conn, snaps, offers)
    # 'level' postes follow a text tier of 'general' (choose.pick): nothing of their own to rank here
    tasks = list(conn.execute("""select * from models.tasks where quality_benchmark is not null
                                 and default_objective <> 'level'"""))
    out: list[dict] = []
    for t in tasks:
        kind = BENCH_KIND[t["quality_benchmark"]]
        if kind not in snaps:
            continue
        bench = list(conn.execute("""select * from models.benchmarks where snapshot_id = %s and benchmark = %s and task = %s""",
                                  (board_snapshot(conn, snaps, t["quality_benchmark"], t["quality_task"]),
                                   t["quality_benchmark"], t["quality_task"])))
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
            elif t["interface"] == "decisions":
                route = decision_route(mo, t["modes"])
                cost_unit = "usd_per_1m_input_tokens"
            else:
                route = media_route(mo, t["interface"], t["modes"])
                cost_unit = (route["paid"] or {}).get("unit")
            if not route["callable"]:
                continue
            cands.append({**b, "route": route, "real_cost": (route["paid"] or {}).get("cost"), "real_cost_unit": cost_unit})
        from .knowledge import tie_break  # late import: knowledge -> choose -> select
        ranked = tie_break(conn, t["task"], _best_by_composite(conn, t, snaps, offers, cands))
        if t["interface"] in MEDIA_EXEC_INTERFACES and t["task"] != "general":
            ranked = _executable_first(conn, t, ranked, offers)
        # the owner: specialised tasks keep only the best model (#2/#3 are useless); general keeps a short list.
        out += [{**r, "rank": i + 1} for i, r in enumerate(ranked[:5 if t["task"] == "general" else 1])]
        if not cands:
            continue
        if t["task"] == "general":
            out += _tier_rows(cands)
    return out


def save(conn, run_id: int, rows: list[dict]) -> None:
    for r in rows:
        conn.execute("""insert into models.selection (run_id, task, level, rank, model_id, variant, display_name, quality,
                        quality_unit, real_cost, cost_unit, provider, offer_key, subscription, reasons)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                     (run_id, r["task"], r["level"], r["rank"], r["model_id"], r["variant"], r["display_name"], r["quality"],
                      r["quality_unit"], r["real_cost"], r["cost_unit"], r["provider"], r["offer_key"], r["subscription"],
                      json.dumps(r["reasons"], default=str)))

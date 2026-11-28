"""Compute ranked candidates per task from the latest snapshots, on the cheapest *real* price.

The Pareto mathematics (make_frontier, ladder_knee) is analysis.pareto, taken over from the aa-pareto-model-optimizer
skill on 2026-10-21.
"""
from __future__ import annotations

import re

import json
from typing import Any

from walter_router.analysis import pareto, parse
from walter_router.analysis import media

DEFAULT_EFFORTS = ("medium", "high")  # assumed effort when a leaderboard lists a model without one (flagged)
MEDIA_UNITS = media.NORM_UNITS   # image per image, video per second, voice per 1000 characters, stt per minute…
BENCH_KIND = {"aa_intelligence": "aa", "aa_eval": "aa_eval", "aa_decision": "aa_decision", "aa_mm": "mm", "da_models": "da", "da_agents": "da", "arena": "arena",
              "bridgebench": "bridgebench", "aa_stt": "aa_stt", "agentset": "agentset", "mteb": "mteb"}


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
    ids = [snaps[k] for k in parse.OFFER_KINDS if k in snaps]
    by_model: dict[str, list[dict]] = {}
    for r in conn.execute("select * from models.offers where snapshot_id = any(%s)", (ids,)):
        by_model.setdefault(r["model_id"], []).append(r)
    return by_model


def blended(offer: dict) -> float | None:
    """AA's blended token price: 3 parts input, 1 part output."""
    if offer["price_in_1m"] is None or offer["price_out_1m"] is None:
        return None
    return (3 * offer["price_in_1m"] + offer["price_out_1m"]) / 4


SUBSCRIPTION_COSTS: dict[tuple[str, str], dict] = {}   # (route provider, model_id) -> cost price (load_subscription_costs)


def load_subscription_costs(conn) -> dict[tuple[str, str], dict]:
    """Cost price of each model through the owner's subscriptions (owner, 2026-11-16: ModelDial's measured quota, see
    plan/modeldial.py): (route provider, model_id) -> {ratio, sub_id}. Several accounts of one provider (two Claude
    accounts) share one plan: the first declared one gives the ratio. Read once per selection run."""
    out: dict[tuple[str, str], dict] = {}
    try:
        from walter_router.plan import subscriptions
        subs = {s["id"]: s for s in subscriptions.load() if s.get("route_provider") and not s.get("retired")}
        for r in conn.execute("select sub_id, detail from models.latest_subscription_costs"):
            sub = subs.get(r["sub_id"])
            for mid, c in ((r["detail"] or {}).get("models") or {}).items():
                if sub and c.get("ratio") and (sub["route_provider"], mid) not in out:
                    out[(sub["route_provider"], mid)] = {"ratio": float(c["ratio"]), "sub_id": r["sub_id"],
                                                         "source": c.get("source")}
    except Exception:  # noqa: BLE001 — no cost price known = the paid routes alone, as before
        return {}
    try:
        out.update(estimate_from_predecessor(out, load_offers(conn, latest_snapshots(conn))))
    except Exception:  # noqa: BLE001 — an estimate is a bonus: the measured ratios stand alone
        pass
    SUBSCRIPTION_COSTS.clear()
    SUBSCRIPTION_COSTS.update(out)
    return out


def _family(model_id: str) -> tuple[tuple[str, ...], tuple[int, ...]]:
    """(line, version) of a model id: gpt-6-2-sol -> (('gpt', 'sol'), (6, 2)); claude-opus-5-5 -> (('claude', 'opus'), (5, 5))."""
    tokens = model_id.split("-")
    return tuple(t for t in tokens if not t.isdigit()), tuple(int(t) for t in tokens if t.isdigit())


def _list_price(offers: list[dict]) -> tuple[float, float] | None:
    o = next((o for o in offers if o["provider"] == "openrouter" and o["interface"] == "chat"
              and o.get("price_in_1m") is not None and o.get("price_out_1m") is not None), None)
    return (float(o["price_in_1m"]), float(o["price_out_1m"])) if o else None


def estimate_from_predecessor(measured: dict, offers: dict) -> dict:
    """Owner, 2026-11-20: a new model of a subscription that ModelDial has not measured yet takes the measured ratio of
    its predecessor — the closest older version of the same line on the same subscription — when both have the SAME
    official API price (input and output per token, OpenRouter's list price). Marked `source: estimated`; a measured
    ratio always wins. GPT-6.2 Sol (2/10 $) takes GPT-6.1 Sol's; GPT-6.2 Astra (8/40 $ vs GPT-6 Astra's 10/50 $) not."""
    est = {}
    for mid, mo in offers.items():
        for prov in {o["provider"] for o in mo if o["access"] == "subscription" and o["interface"] == "chat"}:
            if (prov, mid) in measured:
                continue
            line, version = _family(mid)
            price = _list_price(mo)
            if not version or price is None:
                continue
            older = [(v, m) for (p, m) in measured if p == prov
                     for (ln, v) in [_family(m)] if ln == line and v and v < version]
            if not older:
                continue
            _, pred = max(older)
            if _list_price(offers.get(pred, [])) != price:
                continue
            est[(prov, mid)] = {**measured[(prov, pred)], "source": "estimated", "estimated_from": pred}
    return est


def route_cost(route: dict) -> float | None:
    """Real cost of a chat route: the cheaper of its best paid offer and its subscription's cost price."""
    costs = [c for c in ((route.get("paid") or {}).get("cost"), (route.get("subscription_cost") or {}).get("cost"))
             if c is not None]
    return min(costs, default=None)


def chat_route(offers: list[dict], list_cost: float | None, modes: list[str] | None = None) -> dict[str, Any]:
    """Cheapest paid route for a chat model, scaling AA's list-price task cost by the provider/list price ratio.

    With a list cost, a subscription that serves the model and has a known cost price (SUBSCRIPTION_COSTS) is priced
    too, in `subscription_cost` (list cost x price ÷ API value of the plan's quota); `paid` stays the best paid route,
    the fallback once the quota is spent. route_cost() gives the cheaper of the two.

    The OpenRouter price is the list reference (it mirrors first-party pricing). A provider without a reference
    is kept unscaled (conservative) and flagged. `modes` = inputs the task needs besides text (video understanding:
    ['video']): only offers declaring them count, so a model that cannot read a video is not callable for it.
    """
    need = set(modes or [])
    chat = [o for o in offers if o["interface"] == "chat" and need <= set(o.get("modes") or [])]
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
    sub_cost = None
    if subscription and list_cost is not None:
        mid = next((o.get("model_id") for o in chat if o["access"] == "subscription"), None)
        known = SUBSCRIPTION_COSTS.get((subscription, mid))
        if known:
            sub_cost = {"provider": subscription, "ratio": known["ratio"], "basis": "subscription_cost_price",
                        "sub_id": known["sub_id"], "source": known.get("source"), "cost": list_cost * known["ratio"],
                        **({"estimated_from": known["estimated_from"]} if known.get("estimated_from") else {})}
    return {"paid": best, "subscription": subscription, "subscription_cost": sub_cost,
            "callable": bool(best or subscription)}


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


AA_MEDIA_COST_UNITS = {"usd_per_image": "image", "usd_per_second": "video"}


def media_list_costs(conn, snaps: dict[str, int]) -> dict[tuple[str, str], float]:
    """AA's list price of a media model in the interface's comparable unit (image: $/image, video: $/second), from its
    best-scored row on AA's media boards: (interface, model_id) -> cost. The reference a token-billed offer is
    priced at (media_route)."""
    out: dict[tuple[str, str], float] = {}
    best: dict[tuple[str, str], float] = {}
    if "mm" not in snaps:
        return out
    for r in conn.execute("""select model_id, score, cost, cost_unit from models.benchmarks
                             where snapshot_id = %s and benchmark = 'aa_mm' and cost is not null""", (snaps["mm"],)):
        iface = AA_MEDIA_COST_UNITS.get(r["cost_unit"])
        k = (iface, r["model_id"])
        if iface and (k not in best or (r["score"] or 0) > best[k]):
            best[k], out[k] = r["score"] or 0, r["cost"]
    return out


def _token_billed(o: dict) -> bool:
    pricing = o.get("pricing") if isinstance(o.get("pricing"), dict) else {}
    return any(float(pricing.get(k) or 0) > 0 for k in ("image_output", "completion"))


def media_route(offers: list[dict], interface: str, modes: list[str] | None = None,
                list_cost: float | None = None) -> dict[str, Any]:
    """Cheapest generation offer in the interface's comparable unit (video per second, image per image), restricted
    to the task's generation modes; input fees, upscales, extensions and free auxiliary SKUs never count.

    An OpenRouter offer billed per token (GPT Image 2.6, MAI-Image 2.7…: no price per image) is priced at AA's list
    price per image (`list_cost`, media_list_costs): OpenRouter mirrors first-party pricing, as for chat_route. Without
    it such a model had no comparable cost and newer image models never reached the library (2026-11-20)."""
    want = MEDIA_UNITS.get(interface)
    paid = []
    for o in offers:
        if o["interface"] != interface:
            continue
        f = _fields(o)
        if f["offer_kind"] == "generation" and f["norm_price"] is None and list_cost is not None \
                and o["provider"] == "openrouter" and _token_billed(o):
            f = {**f, "norm_price": list_cost, "norm_unit": want, "basis": "aa_list_price_token_billed"}
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
                reasons={**{k: v for k, v in paid.items() if k not in ("provider", "offer_key")}, **extra,
                         **({"subscription_cost": route["subscription_cost"]} if route.get("subscription_cost") else {})})


def _ladder(cands: list[dict], minimum_score: float, cost_cap: float) -> dict | None:
    rows = [{"name": c["display_name"], "slug": f'{c["model_id"]}|{c["variant"]}', "score": c["score"],
             "cost": c["real_cost"], "_c": c} for c in cands if c.get("real_cost") and c["real_cost"] > 0]
    if len(rows) < 2:
        return None
    frontier = pareto.make_frontier(rows, "score", "cost", minimum_score, 0.5, 0.5, 10.0, 2.0, cost_cap)
    by_slug = {r["slug"]: r["_c"] for r in rows}
    ladder = frontier["upgrade_ladder"]
    if not ladder["tiers"]:
        return None
    knee = pareto.ladder_knee(ladder["tiers"])
    return {"anchor": by_slug[ladder["tiers"][0]["slug"]], "knee": by_slug[knee["slug"]],
            "ceiling": by_slug[(ladder.get("quality_ceiling") or ladder["tiers"][-1])["slug"]],
            "frontier": [by_slug[r["slug"]] for r in frontier["pragmatic_frontier"]]}


QUOTA_WHY = {"L2": "abonnements : meilleur modèle d'un autre abonnement que L3, moins cher par tâche que L3, "
                   "tant que son quota dure",
             "L3": "abonnements : choix de la méthode parmi les modèles d'abonnement, tant que son quota dure"}


def _on_subscription(p: dict) -> bool:
    """The point's real cost is a subscription's cost price (not a paid route)."""
    sub = (p.get("route") or {}).get("subscription_cost")
    return bool(sub) and sub.get("cost") is not None and p.get("cost") == sub["cost"]


def _sub_of(p: dict) -> str | None:
    """Which subscription serves the point at its cost price (two Claude accounts = one route provider)."""
    return ((p.get("route") or {}).get("subscription_cost") or {}).get("provider") if _on_subscription(p) else None


def _without_subscription(pts: list[dict], provider: str) -> list[dict]:
    """The same points once `provider`'s subscription is spent: its models at their best paid price, or gone."""
    out = []
    for p in pts:
        sub = (p.get("route") or {}).get("subscription_cost")
        if sub and sub.get("provider") == provider:
            paid = (p["route"].get("paid") or {}).get("cost")
            if paid:
                out.append({**p, "cost": paid})
        else:
            out.append(p)
    return out


HOLD_WHY = {"move": "même prix que le niveau déclaré (±{band} %), meilleur score",
            "keep": "niveau déclaré gardé : rien de mieux noté au même prix (±{band} %)",
            "keep_l3": "niveau déclaré gardé : la méthode ne trouve pas mieux noté"}


def _spent_fallback(pts: list[dict], p: dict, level: str, picked: dict) -> dict | None:
    """The tier's pick once `p`'s subscription is spent (the 16/11 rule on the remaining pool, else the method)."""
    spent = _without_subscription(pts, p["route"]["subscription_cost"]["provider"])
    if not spent:
        return None
    from walter_router.analysis import tiers
    fb = (tiers.above(spent, _on_subscription, picked["L2"]) if level == "L3" and picked.get("L2")
          else tiers.quota_levels(spent, _on_subscription, _sub_of).get(level))
    return fb or tiers.compute(spent)[level]


def _quota_info(pts, p, level, picked, method_pick) -> dict | None:
    if not _on_subscription(p):
        return None
    sub = p["route"]["subscription_cost"]
    fb = _spent_fallback(pts, p, level, picked)
    return {"subscription": sub["sub_id"], "route_provider": sub["provider"], "method_pick": method_pick,
            "estimated_from": sub.get("estimated_from"),
            "when_quota_spent": fb and {"pin": f'{fb["model_id"]}/{fb["variant"]}', "name": fb["display_name"],
                                        "score": fb["score"], "real_cost": fb["cost"]}}


def _tier_rows(cands: list[dict], pins: dict | None = None) -> list[dict]:
    """The owner's three text tiers (tiers.py) on the AA frontier of callable model x reasoning level, real costs.
    `pins` = the declared tiers {level: (model_id, variant)}: L1/L2 then follow the hold rule (2026-11-20, same price,
    better score), and no tier is proposed below its declared model's score in this same snapshot."""
    from walter_router.analysis import tiers  # late import keeps the module graph flat
    pts = [{**c, "cost": c["real_cost"]} for c in cands if c.get("real_cost")]
    t = tiers.compute(pts)
    q = tiers.quota_levels(pts, _on_subscription, _sub_of)
    pins = pins or {}
    anchors = {lv: next((p for p in pts if (p["model_id"], p["variant"] or "") == tuple(pin)), None)
               for lv, pin in pins.items()}
    band = round(tiers.HOLD_BAND * 100)
    rows, picked = [], {}
    for level, why in (("L1", "économique : premier coude au-dessus du plancher de qualité"),
                       ("L2", "intermédiaire : meilleur gain en points par $ depuis L1"),
                       ("L3", "haut de gamme : meilleur gain depuis L2 dans la bande du plafond")):
        p, m = q.get(level), t[level]
        a = anchors.get(level)
        missing = {"declared_missing": "/".join(pins[level])} if level in pins and not a else {}
        method_pick = m and f'{m["model_id"]}/{m["variant"]}'
        if a and level in ("L1", "L2"):
            l3_sub = _sub_of(anchors["L3"]) if anchors.get("L3") else None
            # L2 keeps the 16/11 spread: never on L3's subscription
            allow = (lambda c: not (l3_sub and _sub_of(c) == l3_sub)) if level == "L2" else (lambda c: True)
            nxt = tiers.hold_price(pts, a, allow=allow)
            pick = nxt or a
            picked[level] = pick
            rows.append(_row("general", level, 1, pick, role=HOLD_WHY["move" if nxt else "keep"].format(band=band),
                             hold={"declared": f'{a["model_id"]}/{a["variant"]}', "declared_score": a["score"],
                                   "declared_cost": a["cost"], "band": tiers.HOLD_BAND,
                                   "gain": round(pick["score"] - a["score"], 2),
                                   "cost_ratio": round(pick["cost"] / a["cost"], 3) if a["cost"] else None},
                             quota_rule=nxt and _quota_info(pts, pick, level, picked, method_pick),
                             method_pick=method_pick, method=t.get("params")))
            continue
        # the rule only ever raises a tier: never below the method's pick, nor at or below L1
        bar = max(m["score"] if m else 0, (t["L1"]["score"] + 1e-9) if t["L1"] else 0)
        if p and p["score"] >= bar:
            # the owner's subscription rule (2026-11-16); once every account of that subscription is spent, the same
            # rule on the remaining subscriptions (L3: the best gain above L2's pick), else the method without it
            pick, role, extra = p, QUOTA_WHY[level], {"quota_rule": _quota_info(pts, p, level, picked, method_pick)}
        elif m:
            pick, role, extra = m, why, {"marginal": m.get("marginal")}
        else:
            continue
        if a and pick["score"] < a["score"] + tiers.HOLD_MIN_GAIN:
            # never a lower score than the declared tier (owner 2026-11-20): it stays
            pick, role, extra = a, HOLD_WHY["keep_l3"], {"method_pick": f'{pick["model_id"]}/{pick["variant"]}'}
        picked[level] = pick
        rows.append(_row("general", level, 1, pick, role=role, method=t.get("params"), **extra, **missing))
    rows += [_row("general", "frontier", i + 1, p, marginal=p.get("marginal"))
             for i, p in enumerate(q for q in t["frontier"] if q["score"] >= tiers.QUALITY_FLOOR - 5)]
    return rows


def _best_by_composite(conn, t: dict, snaps: dict, offers: dict, cands: list[dict], n: int = 6) -> list[dict]:
    """'best' level: callable models ordered by the weighted multi-board score (scoring.composite)."""
    from walter_router.analysis.scoring import composite  # late import (scoring -> select)
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
            route = chat_route(mo, None, t["modes"]) if t["interface"] == "chat" else decision_route(mo, t["modes"]) \
                if t["interface"] == "decisions" else media_route(mo, t["interface"], t["modes"],
                                                                 media_list_costs(conn, snaps).get((t["interface"], mid)))
            if not route["callable"]:
                continue
            cost, variant = route_cost(route) if t["interface"] == "chat" else (route["paid"] or {}).get("cost"), ""
            unit = (route["paid"] or {}).get("unit") if t["interface"] != "chat" else None
        paid = route.get("paid") or {}
        name = conn.execute("select coalesce(display_name, model_id) as n from models.canonical where model_id = %s",
                            (mid,)).fetchone()["n"]
        rows.append(dict(task=t["task"], level="best", rank=len(rows) + 1, model_id=mid, variant=variant,
                         display_name=name, quality=comp["composite"], quality_unit="Composite /100",
                         real_cost=cost, cost_unit=unit, provider=paid.get("provider"), offer_key=paid.get("offer_key"),
                         subscription=route.get("subscription"),
                         reasons={**{k: v for k, v in paid.items() if k not in ("provider", "offer_key")},
                                  "boards": comp["boards"], "evidence_weight": comp["evidence_weight"],
                                  **({"subscription_cost": route["subscription_cost"]} if route.get("subscription_cost") else {})}))
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
    from walter_router.serve.media_exec import _models, supports   # late import (media_exec -> select)
    runnable = {m for m, c in _models(conn).items() if c.get("kind") in ("image", "video", "audio", "music")
                and supports(c, t["modes"])}
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
        # same version (GPT Image 2.6 Flare / Sunburst): the better on the boards this task borrows weight from
        from walter_router.analysis.scoring import composite  # late import (scoring -> select)
        borrowed = {c["model_id"]: c["composite"] for c in composite(conn, t["task"])} if len(newer) > 1 else {}
        newer.sort(key=lambda m: (m in pinned, family(m)[1], borrowed.get(m, -1.0), m), reverse=True)
        if newer:
            name = conn.execute("select coalesce(display_name, model_id) as n from models.canonical where model_id = %s",
                                (newer[0],)).fetchone()
            route = media_route(offers.get(newer[0], []), t["interface"], t["modes"],
                                media_list_costs(conn, latest_snapshots(conn)).get((t["interface"], newer[0])))
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
    load_subscription_costs(conn)
    snaps = latest_snapshots(conn)
    offers = load_offers(conn, snaps)
    if "aa" not in snaps:
        return []
    out = []
    for b in conn.execute("""select model_id, variant, display_name, score, cost from models.benchmarks
                             where snapshot_id = %s and benchmark = 'aa_intelligence'""", (snaps["aa"],)):
        route = chat_route(offers.get(b["model_id"], []), b["cost"])
        cost = route_cost(route)
        if route["callable"] and cost:
            out.append({"model_id": b["model_id"], "variant": b["variant"], "name": b["display_name"],
                        "score": b["score"], "cost": cost, "cost_aa": b["cost"],
                        "provider": (route.get("paid") or {}).get("provider"),
                        "subscription": bool(route.get("subscription"))})
    return out


def _declared_tiers(conn) -> dict:
    """The owner's declared text tiers as pinned (knowledge.json "levels", re-applied to preferences each cycle)."""
    return {r["role"]: (r["pinned_model_id"], r["pinned_variant"] or "") for r in conn.execute(
        """select role, pinned_model_id, pinned_variant from models.preferences
           where task = 'general' and role in ('L1', 'L2', 'L3') and pinned_model_id is not null""")}


def compute(conn) -> list[dict]:
    load_subscription_costs(conn)
    snaps = latest_snapshots(conn)
    offers = load_offers(conn, snaps)
    intel = _intelligence_index(conn, snaps, offers)
    list_costs = media_list_costs(conn, snaps)
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
                route = chat_route(mo, list_cost, t["modes"])
                cost_unit = "usd_per_aa_task" if list_cost is not None else None
                if assumed:
                    route = {**route, "paid": {**(route["paid"] or {}), "cost_basis_effort_assumed": assumed}}
            elif t["interface"] == "decisions":
                route = decision_route(mo, t["modes"])
                cost_unit = "usd_per_1m_input_tokens"
            else:
                route = media_route(mo, t["interface"], t["modes"], list_costs.get((t["interface"], b["model_id"])))
                cost_unit = (route["paid"] or {}).get("unit")
            if not route["callable"]:
                continue
            real = route_cost(route) if t["interface"] == "chat" else (route["paid"] or {}).get("cost")
            cands.append({**b, "route": route, "real_cost": real, "real_cost_unit": cost_unit})
        from walter_router.analysis.knowledge import tie_break  # late import: knowledge -> choose -> select
        ranked = tie_break(conn, t["task"], _best_by_composite(conn, t, snaps, offers, cands))
        if t["interface"] in MEDIA_EXEC_INTERFACES and t["task"] != "general":
            ranked = _executable_first(conn, t, ranked, offers)
        # the owner: specialised tasks keep only the best model (#2/#3 are useless); general keeps a short list.
        out += [{**r, "rank": i + 1} for i, r in enumerate(ranked[:5 if t["task"] == "general" else 1])]
        if not cands:
            continue
        if t["task"] == "general":
            out += _tier_rows(cands, _declared_tiers(conn))
    return out


def save(conn, run_id: int, rows: list[dict]) -> None:
    for r in rows:
        conn.execute("""insert into models.selection (run_id, task, level, rank, model_id, variant, display_name, quality,
                        quality_unit, real_cost, cost_unit, provider, offer_key, subscription, reasons)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                     (run_id, r["task"], r["level"], r["rank"], r["model_id"], r["variant"], r["display_name"], r["quality"],
                      r["quality_unit"], r["real_cost"], r["cost_unit"], r["provider"], r["offer_key"], r["subscription"],
                      json.dumps(r["reasons"], default=str)))

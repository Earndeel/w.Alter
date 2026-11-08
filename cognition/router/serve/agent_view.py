"""What an agent sees of a routing decision: the choice, why, and every execution route with what a million tokens
costs there — the same view in every runtime (Hermes plugin, walter MCP). The full decision stays for the runners."""
from __future__ import annotations

KEEP = ("task", "mode", "role", "role_label", "matched_signals", "model_id", "variant", "display_name", "provider",
        "level", "objective", "quality", "quality_unit", "real_cost", "cost_unit", "why", "warning", "require",
        "score_from_base", "unrestricted_signals", "role_source")


def view(d: dict) -> dict:
    out = {k: d[k] for k in KEEP if d.get(k) not in (None, [], "")}
    if d.get("profile"):
        out["profile"] = {k: v for k, v in d["profile"].items() if v}
    if d.get("execution"):
        out["execution"] = [route_line(e) for e in d["execution"][:6]]
    route = d.get("route") or {}
    if route.get("paid") and not d.get("execution"):   # media decisions only: a chat model's cost is per route
        out["media_route"] = {k: route["paid"].get(k) for k in ("provider", "offer_key", "cost", "unit", "by_resolution")}
    if d.get("ui"):
        out["ui"] = d["ui"]
    if d.get("web"):
        out["web"] = {k: d["web"][k] for k in ("service", "why", "fallback_mode") if d["web"].get(k)}
    if isinstance(d.get("intent"), dict):
        out["intent"] = {k: d["intent"].get(k) for k in ("task", "task_confidence", "video_role", "level",
                                                          "unrestricted", "error") if d["intent"].get(k) is not None}
    if d.get("brief"):
        out["brief"] = d["brief"]
    if d.get("alternatives"):
        out["alternatives"] = d["alternatives"][:5]
    return out


def route_line(e: dict) -> dict:
    """One execution route as the agent needs it: who runs it, and what a million tokens costs there (in / out):
    the subscription's cost price while its quota lasts, else the host's or provider's price."""
    line = {k: e.get(k) for k in ("provider", "hermes_provider", "model", "reasoning", "probe_ok", "fallback_for")
            if e.get(k) is not None}
    sub = e.get("subscription") or {}
    price = e.get("cost_price_1m") or ({"in": e["host"]["price_in_1m"], "out": e["host"]["price_out_1m"]}
                                       if (e.get("host") or {}).get("price_in_1m") is not None else None)
    if price:
        line["usd_per_1m"] = {k: round(v, 4) for k, v in price.items() if v is not None}
    elif e.get("blended_1m") is not None:
        line["usd_per_1m_blended"] = round(e["blended_1m"], 4)
    if sub:
        line["subscription"] = {"plan": sub.get("plan"), "quota_used_percent": sub.get("quota_used_percent")}
    if (e.get("host") or {}).get("host"):
        line["host"] = e["host"]["host"]
    return line

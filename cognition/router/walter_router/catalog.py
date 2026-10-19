"""Model cards: what a model does, what it costs per resolution, where to call it and how it ranks — and the
one-line rendering Monsieur reads on Telegram ("FLUX.3 Image — t2i/i2i — 1K 0,03 · 4K 0,12 $/img — OpenRouter")."""
from __future__ import annotations

from . import media

UNIT_SHORT = {"per second": "$/s", "per image": "$/img", "per song": "$/titre", "per 1000 characters": "$/1k car.",
              "per request": "$/requête", "per minute": "$/min", "per search": "$/recherche",
              "per 1m tokens": "$/M tokens"}
PROVIDERS = {"openrouter": "OpenRouter", "kie": "Kie", "codex": "Codex", "google-flow": "Flow"}
BOARDS = {"aa_intelligence": "AA", "aa_decision": "AA Decision", "aa_mm": "AA", "da_models": "Design Arena", "da_agents": "Design Arena",
          "arena": "Arena", "bridgebench": "BridgeBench", "aa_stt": "AA STT", "agentset": "Agentset", "mteb": "MTEB"}
MAX_LISTED_RESOLUTIONS = 4
ICONS = {"image": "🖼️", "video": "🎬", "audio": "🗣️", "music": "🎵", "chat": "💬", "transcription": "🎙️",
         "embedding": "🧭", "rerank": "🔀"}


def card(conn, model_id: str, interface: str, modes: list[str] | None = None) -> dict:
    """Everything known about one model on one interface, from the latest snapshots."""
    row = conn.execute("select * from models.catalog where model_id = %s and interface = %s",
                       (model_id, interface)).fetchone()
    name = conn.execute("select coalesce(display_name, model_id) as n from models.canonical where model_id = %s",
                        (model_id,)).fetchone()
    prices: dict[str, dict] = {}
    audio: set = set()
    token_priced = bool(conn.execute("""select 1 from models.offers o join models.latest_snapshots s using (snapshot_id)
                                        where o.model_id = %s and o.interface = %s and o.unit_price is not null
                                        and o.unit ilike '%%token%%' limit 1""", (model_id, interface)).fetchone())
    for o in conn.execute("""select o.provider, o.modes, o.resolution, o.audio, o.norm_price, o.norm_unit
                             from models.offers o join models.latest_snapshots s using (snapshot_id)
                             where o.model_id = %s and o.interface = %s and o.offer_kind = 'generation'
                             and o.norm_price is not null""", (model_id, interface)):
        if not media.compatible(o["modes"], modes):
            continue
        res = o["resolution"] or ""
        if res not in prices or o["norm_price"] < prices[res]["price"]:
            prices[res] = {"price": o["norm_price"], "provider": o["provider"], "unit": o["norm_unit"]}
        audio.add(o["audio"])
    if not prices:  # nothing in the comparable unit: show the provider's own unit rather than "no price"
        raw = conn.execute("""select o.provider, o.unit_price, o.unit from models.offers o
                              join models.latest_snapshots s using (snapshot_id)
                              where o.model_id = %s and o.interface = %s and o.offer_kind = 'generation'
                              and o.unit_price > 0 and o.unit not ilike '%%token%%'
                              order by o.unit_price limit 1""", (model_id, interface)).fetchone()
        if raw:
            prices[""] = {"price": raw["unit_price"], "provider": raw["provider"], "unit": raw["unit"].strip().lower()}
    price_in = row["price_in_1m"] if row else None
    if interface == "decisions" and price_in is None:   # the catalog view prices chat only; decisions bill input tokens
        p = conn.execute("""select min(o.price_in_1m) as p from models.offers o join models.latest_snapshots s
                            using (snapshot_id) where o.model_id = %s and o.interface = 'decisions'""", (model_id,)).fetchone()
        price_in = p["p"] if p else None
    return {"model_id": model_id, "interface": interface, "name": name["n"] if name else model_id,
            "modes": list(row["modes"]) if row else [], "providers": list(row["providers"]) if row else [],
            "released": row["released"] if row else None, "scores": row["scores"] if row else {},
            "prices": dict(sorted(prices.items(), key=lambda kv: media.resolution_rank(kv[0]))),
            "audio": sorted(a for a in audio if a is not None), "token_priced": token_priced,
            "content_policy": row["content_policy"] if row else "standard",
            "price_in_1m": price_in, "price_out_1m": row["price_out_1m"] if row else None,
            "subscriptions": list(row["subscriptions"]) if row and row["subscriptions"] else [],
            "open_weights": row["open_weights"] if row else None}


def money(x: float) -> str:
    """0.0525 -> '0,053' ; 1.2 -> '1,2' (French decimals, 2 significant digits under 1 $)."""
    s = f"{x:.2g}" if x < 1 else f"{x:.2f}".rstrip("0").rstrip(".")
    if "e" in s:
        s = f"{x:.4f}".rstrip("0")
    return s.replace(".", ",")


def price_text(c: dict) -> str:
    if c.get("interface") == "decisions" and c.get("price_in_1m") is not None:
        return f'{money(c["price_in_1m"])} $ par M tokens d’entrée'
    if c.get("interface") == "chat" and c.get("price_in_1m") is not None:
        sub = " (inclus abonnement)" if c.get("subscriptions") else ""
        return f'{money(c["price_in_1m"])}/{money(c["price_out_1m"])} $ par M tokens{sub}'
    if not c["prices"]:
        return "tarif au token" if c.get("token_priced") else "prix non publié"
    items = list(c["prices"].items())
    if len(items) > 1:
        items = [kv for kv in items if kv[0]] or items  # an unlabelled SKU next to per-resolution ones adds nothing
    raw_unit = items[0][1]["unit"] or ""
    unit = UNIT_SHORT.get(raw_unit, f'$ {raw_unit.replace("per ", "/")}'.strip())
    if len(items) == 1 or len(items) > MAX_LISTED_RESOLUTIONS:
        lo, hi = items[0], items[-1]
        if len(items) == 1:
            text = f'{(lo[0] + " ") if lo[0] else ""}{money(lo[1]["price"])} {unit}'
        else:
            text = f'{money(min(v["price"] for _, v in items))}–{money(max(v["price"] for _, v in items))} {unit}' \
                   f' ({lo[0] or "?"}→{hi[0] or "?"})'
    else:
        text = " · ".join(f'{r or "?"} {money(v["price"])}' for r, v in items) + f" {unit}"
    if c["audio"] == [False, True]:
        text += " (son en option)"
    elif c["audio"] == [True]:
        text += " (son inclus)"
    return text


def icon(c: dict) -> str:
    """🖼️ image, 🎬 video, 🗣️ voice, 🎵 music, 💬 text; 🔓 added for an unrestricted model."""
    return ICONS.get(c["interface"], "•") + (" 🔓" if c.get("content_policy") == "unrestricted" else "")


def line(c: dict) -> str:
    parts = [f'{icon(c)} {c["name"]}']
    if c["modes"]:
        parts.append(media.short_modes(c["modes"]))
    parts.append(price_text(c))
    if c["providers"]:
        parts.append(", ".join(PROVIDERS.get(p, p) for p in c["providers"]))
    return " — ".join(parts)

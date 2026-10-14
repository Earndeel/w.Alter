"""The model library as Monsieur reads it (2026-10-14): per task and category, the model in use, who chose it, the
measured #1 when it differs, providers in order with prices, the fallback model, subscriptions, warnings.

`walter-router library [--json]`. Text tiers L1/L2/L3 follow Monsieur's Pareto method (never flagged as « ≠ n°1 »).
"""
from __future__ import annotations

from . import catalog, choose, media_exec, scoring
from . import select as sel

PROV = {"openai-codex": "Codex (abonnement)", "codex": "Codex (abonnement)", "kie-codex": "Kie", "kie": "Kie",
        "openrouter": "OpenRouter", "arnict": "Arnict", "google-flow": "Flow"}
MODES = {"text_to_video": "t2v", "image_to_video": "i2v", "text_to_image": "t2i", "image_edit": "i2i", "logo": "t2i",
         "graphic_design": "t2i", "music": "music", "tts": "tts", "video_edit": "v2v"}
ROLE_ORDER = "case p.role when 'default' then 0 when 'L1' then 0 when 'L2' then 1 when 'L3' then 2 else 5 end"


def _name(conn, mid: str | None) -> str:
    if not mid:
        return "—"
    r = conn.execute("select coalesce(display_name, model_id) as n from models.canonical where model_id = %s",
                     (mid,)).fetchone()
    return r["n"] if r else mid


def _chat_price(offers: dict, mid: str, prov: str) -> str:
    key = {"kie-codex": "kie", "openai-codex": "codex"}.get(prov, prov)
    if key == "codex":
        return "inclus"
    p = [o for o in offers.get(mid, []) if o["interface"] == "chat" and o["provider"] == key
         and o.get("price_in_1m") is not None]
    return f'{catalog.money(p[0]["price_in_1m"])}/{catalog.money(p[0]["price_out_1m"])} $/M' if p else ""


def _media_price(offers: dict, mid: str, prov: str, interface: str) -> str:
    own = [o for o in offers.get(mid, []) if o["provider"] == prov and o["interface"] == interface
           and o.get("offer_kind") == "generation" and o.get("norm_price") is not None]
    if not own:
        return "au token" if prov == "openrouter" and interface == "image" else ""
    lo, hi = min(o["norm_price"] for o in own), max(o["norm_price"] for o in own)
    unit = catalog.UNIT_SHORT.get(own[0].get("norm_unit") or "", "$")
    return f'{catalog.money(lo)}{"–" + catalog.money(hi) if hi != lo else ""} {unit}'


def rows(conn) -> list[dict]:
    from .cli import with_execution   # late import (cli -> library)
    offers = sel.load_offers(conn, sel.latest_snapshots(conn))
    runnable = set(media_exec._models())
    out = []
    for e in conn.execute(f"""select t.task, t.label, t.interface, t.modes, p.role, p.pinned_model_id, p.label as role_label
                              from models.tasks t left join models.preferences p using (task)
                              where t.interface <> 'tool' order by t.interface, t.task, {ROLE_ORDER}, p.priority"""):
        task, role, iface = e["task"], e["role"], e["interface"]
        row = {"type": iface, "task": task, "label": e["label"],
               "category": e["role_label"] or ("" if role in (None, "default") else role),
               "warning": None}
        try:
            d = choose.pick(conn, task, level=role if task == "general" else None,
                            role=None if task == "general" else role)
        except Exception as exc:  # noqa: BLE001
            out.append({**row, "model": None, "warning": f"aucun modèle ({type(exc).__name__})"})
            continue
        mid = d.get("model_id")
        sel_row = conn.execute("""select model_id, reasons from models.selection where run_id = (select run_id from
                                  models.latest_run) and task = %s and level = 'best' and rank = 1""", (task,)).fetchone()
        comp = scoring.composite(conn, task) if task != "general" else []
        if iface == "decisions":   # the AA Decision Index also lists LLMs: compare decision models only
            need = set(e["modes"] or [])
            comp = [c for c in comp if any(o["interface"] == "decisions" and need <= set(o.get("modes") or [])
                                           for o in offers.get(c["model_id"], []))]
        top = comp[0] if comp else None
        row.update(model=_name(conn, mid) + (f' ({d["variant"]})' if d.get("variant") else ""), model_id=mid,
                   chosen_by="méthode des niveaux" if task == "general" else
                   ("toi" if e["pinned_model_id"] else "calcul"),
                   measured_first=_name(conn, top["model_id"]) if top else None,
                   measured_first_score=round(top["composite"]) if top else None,
                   score=next((round(c["composite"]) for c in comp if c["model_id"] == mid), None))
        if sel_row and (sel_row["reasons"] or {}).get("warning") and sel_row["model_id"] == mid:
            row["warning"] = sel_row["reasons"]["warning"]
        if task == "decision_vision":
            row["warning"] = "AA ne teste pas encore la vision : classé sur l'index texte, parmi ceux qui lisent les images"
        if top and task != "general" and top["model_id"] != mid:
            if iface in sel.MEDIA_EXEC_INTERFACES and top["model_id"] not in runnable:
                why = " (pas de fournisseur branché)"
            elif not any(o["interface"] == iface for o in offers.get(top["model_id"], [])):
                why = " (proposé par aucun de nos fournisseurs)"
            else:
                why = ""
            row["differs"] = f'n°1 mesuré : {_name(conn, top["model_id"])} ({round(top["composite"])}){why}'
        if iface == "chat":
            d = with_execution(conn, d)
            ex = d.get("execution") or []
            main, fb = [r for r in ex if not r.get("fallback_for")], [r for r in ex if r.get("fallback_for")]
            row["providers"] = " → ".join(f'{PROV.get(r["hermes_provider"], r["hermes_provider"])} '
                                          f'{_chat_price(offers, mid, r["hermes_provider"])}'.strip() for r in main)
            row["fallback"] = (f'{fb[0]["model"]}{" " + fb[0]["reasoning"] if fb[0].get("reasoning") else ""} via '
                               f'{PROV.get(fb[0]["hermes_provider"], fb[0]["hermes_provider"])}') if fb else "—"
            row["subscription"] = "Codex" if any(r["access"] == "subscription" for r in main) else \
                ("Codex (secours)" if any(r["access"] == "subscription" for r in fb) else "—")
        elif iface in sel.MEDIA_EXEC_INTERFACES:
            cfg = media_exec._models().get(mid) or {}
            mode = MODES.get(task)
            order = media_exec.choose_provider(conn, mid, iface, None, bool((cfg.get("kie") or {}).get(mode)),
                                               media_exec.openrouter_id(conn, mid)) if cfg else []
            provs = " → ".join(f'{PROV.get(p, p)} {_media_price(offers, mid, p, iface)}'.strip() for p in order)
            flow = d.get("mode") == "manual_ui" or d.get("provider") == "google-flow"
            row["providers"] = (f"Flow à la main → {provs} (si payant)" if flow else provs) or "pas de fournisseur branché"
            fb = media_exec.fallback_models(conn, task, role, mid, mode, n=1) if cfg else []
            row["fallback"] = _name(conn, fb[0]) if fb else "—"
            row["subscription"] = "Gemini AI Pro (crédits Flow)" if flow else "—"
        else:   # decisions
            o = [x for x in offers.get(mid, []) if x["interface"] == "decisions" and x.get("price_in_1m") is not None]
            row["providers"] = f'OpenRouter {catalog.money(o[0]["price_in_1m"])} $/M' if o else "OpenRouter"
            row["fallback"] = "Mercury Decide (gratuit) → Clef"
            row["subscription"] = "—"
        out.append(row)
    return out


def render(rs: list[dict]) -> str:
    titles = {"chat": "💬 Texte", "image": "🖼️ Image", "video": "🎬 Vidéo", "audio": "🗣️ Audio", "music": "🎵 Musique",
              "decisions": "🧭 Décision"}
    lines, cur = [], None
    for r in rs:
        if r["type"] != cur:
            cur = r["type"]
            lines += ["", titles.get(cur, cur)]
        head = f'• {r["label"]}' + (f' › {r["category"]}' if r["category"] and r["task"] != "general" else
                                     (f' › {r["category"]}' if r["category"] else ""))
        if not r.get("model"):
            lines.append(f'{head} : ⚠️ {r.get("warning") or "aucun modèle"}')
            continue
        mark = "⭐ ton choix" if r["chosen_by"] == "toi" else ("📐 méthode des niveaux" if r["chosen_by"] ==
                                                            "méthode des niveaux" else "🤖 calculé")
        lines.append(f'{head} : {r["model"]}  [{mark}]')
        if r.get("differs"):
            lines.append(f'   ≠ {r["differs"]}')
        if r.get("warning"):
            lines.append(f'   ⚠️ {r["warning"]}')
        lines.append(f'   Fournisseurs : {r.get("providers") or "—"} · Secours : {r.get("fallback") or "—"}'
                     + (f' · Abonnement : {r["subscription"]}' if r.get("subscription") not in (None, "—") else ""))
    return "\n".join(lines).strip()

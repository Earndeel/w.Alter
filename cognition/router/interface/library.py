"""The model library as the owner reads it (2026-10-14): per task and category, the model in use, who chose it, the
measured #1 when it differs, providers in order with prices, the fallback model, subscriptions, warnings.

`walter-router library [--json]`. Text tiers L1/L2/L3 follow the owner's Pareto method (never flagged as « ≠ n°1 »).
"""
from __future__ import annotations

import re

from walter_router import paths
from walter_router.analysis import catalog
from walter_router.serve import choose
from walter_router.serve import media_exec
from walter_router.analysis import scoring
from walter_router.analysis import select as sel
from walter_router import instance

PROV = {"openai-codex": "Codex (abonnement)", "codex": "Codex (abonnement)", "kie-codex": "Kie", "kie": "Kie",
        "openrouter": "OpenRouter", "arnict": "Arnict", "google-flow": "Flow"}
MODES = {"text_to_video": "t2v", "image_to_video": "i2v", "text_to_image": "t2i", "image_edit": "i2i", "logo": "t2i",
         "graphic_design": "t2i", "music": "music", "tts": "tts", "video_edit": "v2v"}
IMAGE_TOKENS = (1056, 4160)   # medium / high 1024x1024 output tokens (OpenAI gpt-image token tables)
ROLE_ORDER = "case p.role when 'default' then 0 when 'L1' then 0 when 'L2' then 1 when 'L3' then 2 else 5 end"


def _name(conn, mid: str | None) -> str:
    if not mid:
        return "—"
    r = conn.execute("select display_name from models.canonical where model_id = %s", (mid,)).fetchone()
    name = r["display_name"] if r else None
    if name and name != mid and not re.fullmatch(r"[a-z0-9.\-]+", name):   # a real name, not a slug like 'muse-wonder-1.0'
        return name
    mid = re.sub(r"(?<=\d)-(?=\d)", ".", name or mid)   # version digits: 1-0 -> 1.0
    # no display name (e.g. a Design Arena-only id 'muse-wonder-1.0'): readable fallback 'Muse Wonder 1.0'
    return " ".join(w.upper() if len(w) <= 3 and not w[:1].isdigit() and w.isalpha() and w in ("gpt", "ai") else
                    (w if w[:1].isdigit() else w.capitalize()) for w in mid.replace("_", "-").split("-"))


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
        if prov == "openrouter" and interface == "image":   # billed per image-output token: estimate per image
            tok = [float((o.get("pricing") or {}).get("image_output") or 0) for o in offers.get(mid, [])
                   if o["provider"] == "openrouter" and o["interface"] == "image"]
            tok = max(tok, default=0)
            if tok:   # ~1 000 (medium) to ~4 000 (high) image tokens for 1024² (OpenAI image token tables)
                return f"≈ {catalog.money(tok * IMAGE_TOKENS[0])}–{catalog.money(tok * IMAGE_TOKENS[1])} $/img estimé"
            return "au token"
        raw = [o for o in offers.get(mid, []) if o["provider"] == prov and o["interface"] == interface
               and o.get("unit_price") and "token" in (o.get("unit") or "")]
        if raw:   # token-priced audio (e.g. Gemini TTS on Kie: input / audio output per M tokens)
            return " / ".join(f'{catalog.money(o["unit_price"])}' for o in sorted(raw, key=lambda o: o["unit_price"])[:2]) \
                + " $/M tokens"
        return ""
    lo, hi = min(o["norm_price"] for o in own), max(o["norm_price"] for o in own)
    unit = catalog.UNIT_SHORT.get(own[0].get("norm_unit") or "", "$")
    return f'{catalog.money(lo)}{"–" + catalog.money(hi) if hi != lo else ""} {unit}'


def sel_model_id(route: dict) -> str:
    """Canonical model id of an execution route ('openai/gpt-6.1-sol', 'gpt-6-1-sol' -> 'gpt-6-1-sol')."""
    from walter_router.analysis import identity
    m = route.get("model_id") or route.get("model") or ""
    return identity.normalize("openrouter", m)[0] if "/" in m else identity.canon(m.replace(".", "-"))


SERVICE_UNITS = {"per minute": "$/min", "per search": "$/recherche", "per 1m tokens": "$/M tokens", "per hour": "$/h"}


def _service_price(offers: dict, mid: str, prov: str, iface: str) -> str:
    own = [o for o in offers.get(mid, []) if o["provider"] == prov and o["interface"] == iface]
    unit = [o for o in own if o.get("norm_price") is not None]
    if unit:
        o = min(unit, key=lambda o: o["norm_price"])
        return f'{catalog.money(o["norm_price"])} {SERVICE_UNITS.get((o.get("norm_unit") or "").lower(), o.get("norm_unit") or "")}'.strip()
    tok = [o for o in own if o.get("price_in_1m") is not None]
    if tok:
        return f'{catalog.money(min(o["price_in_1m"] for o in tok))} $/M tokens audio' if iface == "transcription" \
            else f'{catalog.money(min(o["price_in_1m"] for o in tok))} $/M tokens'
    return ""


BENCH_TASK = {  # bench_task -> (fr, en)
    "text_to_video": ("vidéo depuis texte", "text to video"), "image_to_video": ("animation d'image", "image to video"),
    "text_to_image": ("image", "text to image"), "image_edit": ("retouche d'image", "image editing"),
    "video_edit": ("édition vidéo", "video editing"), "tts": ("voix", "text to speech"),
    "speech_to_speech": ("conversation vocale", "speech to speech"), "text": ("texte", "text"),
    "text_french": ("texte en français", "French text"), "text_coding": ("code", "coding"),
    "webdev": ("développement web", "web development"), "document": ("documents", "documents"), "vision": ("vision", "vision"),
    "3d": ("3D", "3D"), "dataviz": ("dataviz", "dataviz"), "website": ("sites web", "websites"),
    "fullstack": ("full-stack", "full-stack"), "gamedev": ("jeux", "games"), "graphicdesign": ("graphisme", "graphic design"),
    "logo": ("logo", "logo"), "mobileapps": ("applis mobiles", "mobile apps"), "svg": ("SVG", "SVG"),
    "uicomponent": ("composants d'interface", "UI components"), "overall": ("global", "overall"),
    "backend": ("back-end", "back-end"), "frontend": ("front-end", "front-end"),
    "intelligence": ("Intelligence Index", "Intelligence Index"), "decision": ("Decision Index", "Decision Index"),
    "wer": ("taux d'erreur (WER)", "word error rate"), "speed": ("vitesse", "speed"), "rerank": ("qualité", "quality"),
    "rerank_speed": ("vitesse", "speed"), "embeddings": ("qualité", "quality"),
    "retrieval_fr": ("recherche en français", "French retrieval"), "trustworthiness": ("fiabilité", "trustworthiness"),
    "healthbench": ("HealthBench", "HealthBench"), "healthbench_pro": ("HealthBench Professional", "HealthBench Professional"),
    "harvey_lab": ("Harvey LAB (juridique)", "Harvey LAB (legal)"), "critpt": ("CritPt (physique)", "CritPt (physics)"),
    "gpqa": ("GPQA Diamond", "GPQA Diamond"), "scicode": ("SciCode", "SciCode"), "hle": ("Humanity's Last Exam", "Humanity's Last Exam"),
    "lcr": ("long contexte (LCR)", "long context (LCR)"), "text_creative": ("écriture créative", "creative writing"),
    "music_vocals": ("musique chantée", "vocal music"), "music_instrumental": ("musique instrumentale", "instrumental music"),
    "aa_3d": ("AA-3D", "AA-3D"), "mmmu_pro": ("MMMU-Pro", "MMMU-Pro")}


def boards_of(conn, task: str) -> tuple[str, str]:
    """« Arena vidéo depuis texte 50 % · AA vidéo depuis texte 50 % » (fr, en): the weighted leaderboards behind the
    task's score (2026-10-17: show which benchmarks compare the models of a category)."""
    fr, en = [], []
    for b in conn.execute("""select benchmark, bench_task, weight from models.task_benchmarks where task = %s and weight > 0
                             order by weight desc, benchmark""", (task,)):
        src = catalog.BOARDS.get(b["benchmark"], b["benchmark"])
        t_fr, t_en = BENCH_TASK.get(b["bench_task"], (b["bench_task"].replace("_", " "),) * 2)
        w = f'{round(b["weight"] * 100)}\u202f%'
        fr.append(f"{src} {t_fr} {w}")
        en.append(f"{src} {t_en} {w}")
    return " · ".join(fr), " · ".join(en)


def rows(conn) -> list[dict]:
    from walter_router.cli import with_execution   # late import (cli -> library)
    offers = sel.load_offers(conn, sel.latest_snapshots(conn))
    runnable = set(media_exec._models())
    out = []
    for e in conn.execute(f"""select t.task, t.label, t.interface, t.modes, p.role, p.pinned_model_id, p.label as role_label
                              from models.tasks t left join models.preferences p using (task)
                              where t.interface <> 'tool' order by t.interface, t.task, {ROLE_ORDER}, p.priority"""):
        task, role, iface = e["task"], e["role"], e["interface"]
        bfr, ben = boards_of(conn, task)
        row = {"type": iface, "task": task, "label": e["label"], "boards": bfr, "boards_en": ben,
               "category": e["role_label"] or ("" if role in (None, "default") else role),
               "warning": None}
        try:
            d = choose.pick(conn, task, level=role if task == "general" else None,
                            role=None if task == "general" else role)
        except Exception as exc:  # noqa: BLE001
            out.append({**row, "model": None, "warning": f"aucun modèle ({type(exc).__name__})"})
            continue
        mid = d.get("model_id")
        if not mid:
            out.append({**row, "model": None, "chosen_by": "calcul", "warning": "aucun modèle exécutable"})
            continue
        sel_row = conn.execute("""select model_id, reasons from models.selection where run_id = (select run_id from
                                  models.latest_run) and task = %s and level = 'best' and rank = 1""", (task,)).fetchone()
        comp = scoring.composite(conn, task) if task != "general" else []
        if iface == "decisions":
            raw = conn.execute("""select max(b.score) s from models.benchmarks b where b.benchmark = 'aa_decision'
                                  and b.snapshot_id = (select snapshot_id from models.latest_snapshots where kind = 'aa_decision')
                                  and b.model_id = %s""", (mid,)).fetchone() if mid else None
            row["score_raw"] = round(raw["s"], 1) if raw and raw["s"] else None
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
            fb_name = _name(conn, sel_model_id(fb[0])) if fb else ""
            row["fallback"] = (f'{fb_name}{" " + fb[0]["reasoning"] if fb[0].get("reasoning") else ""} via '
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
        elif iface in ("transcription", "embedding", "rerank"):   # STT, embeddings, rerank (2026-10-17): priced per minute / search / M tokens
            row["providers"] = " → ".join(
                f'{PROV.get(p, p)} {_service_price(offers, mid, p, iface)}'.strip()
                for p in dict.fromkeys(o["provider"] for o in offers.get(mid, []) if o["interface"] == iface)) or "—"
            nxt = next((c["model_id"] for c in comp if c["model_id"] != mid
                        and any(o["interface"] == iface for o in offers.get(c["model_id"], []))), None)
            row["fallback"] = _name(conn, nxt) if nxt else "—"
            row["subscription"] = "—"
        else:   # decisions
            o = [x for x in offers.get(mid, []) if x["interface"] == "decisions" and x.get("price_in_1m") is not None]
            row["providers"] = f'OpenRouter {catalog.money(o[0]["price_in_1m"])} $/M' if o else "OpenRouter"
            row["fallback"] = "Mercury Decide (gratuit) → Clef"
            row["subscription"] = "—"
        if row.get("score_raw") is not None:
            row["score"] = row.pop("score_raw")
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


# --- HTML page (Cloudflare Pages, behind Cloudflare Access; 2026-10-14) -----------------------------

def _context(conn) -> dict:
    run = conn.execute("select run_id, started_at, finished_at from models.runs where status = 'ok' "
                       "order by run_id desc limit 1").fetchone()
    counts = {r["interface"]: r["n"] for r in conn.execute(
        "select interface, count(distinct model_id) n from models.catalog group by 1")}
    down = [dict(r) for r in conn.execute("""select subject, evidence from models.alerts where kind = 'board_down'
                                             and status in ('open', 'notified') order by subject""")]
    return {"run": dict(run) if run else {}, "counts": counts, "down": down,
            "tracked": conn.execute("select count(*) n from models.canonical").fetchone()["n"]}


def render_html(rs: list[dict], ctx: dict) -> str:
    import html
    from datetime import datetime, timezone
    esc = html.escape
    titles = {"chat": ("💬", "Texte"), "image": ("🖼️", "Image"), "video": ("🎬", "Vidéo"), "audio": ("🗣️", "Audio"),
              "music": ("🎵", "Musique"), "decisions": ("🧭", "Décision")}
    order = ["chat", "image", "video", "audio", "music", "decisions"]
    badge = {"toi": ("star", "⭐ Ton choix"), "calcul": ("calc", "🤖 Calculé"),
             "méthode des niveaux": ("tier", "📐 Méthode des niveaux")}

    def chips(text: str | None) -> str:
        if not text or text == "—":
            return '<span class="muted">—</span>'
        parts = [p.strip() for p in text.split("→")]
        return '<span class="arrow">→</span>'.join(f'<span class="chip">{esc(p)}</span>' for p in parts)

    sections = []
    for t in order:
        items = [r for r in rs if r["type"] == t]
        if not items:
            continue
        cards = []
        for r in items:
            cls, label = badge.get(r.get("chosen_by") or "", ("calc", "🤖 Calculé"))
            differs = bool(r.get("differs")) and r.get("chosen_by") == "toi"
            search = " ".join(str(r.get(k) or "") for k in ("label", "category", "model", "providers", "fallback"))
            body = [f'<div class="task">{esc(r["label"])}'
                    + (f' <span class="cat">› {esc(r["category"])}</span>' if r.get("category") else "") + "</div>"]
            if not r.get("model"):
                body.append(f'<div class="model none">Aucun modèle</div><div class="warn">⚠️ {esc(r.get("warning") or "")}</div>')
            else:
                body.append(f'<div class="model">{esc(r["model"])}</div><span class="badge {cls}">{label}</span>'
                            + (f'<span class="score">score {r["score"]}</span>' if r.get("score") is not None
                               and r.get("chosen_by") != "méthode des niveaux" else ""))
                if r.get("differs"):
                    body.append(f'<div class="differs">≠ {esc(r["differs"])}</div>')
                if r.get("warning"):
                    body.append(f'<div class="warn">⚠️ {esc(r["warning"])}</div>')
                body.append(f'<div class="row"><span class="k">Fournisseurs</span><span>{chips(r.get("providers"))}</span></div>')
                body.append(f'<div class="row"><span class="k">Secours</span><span>{chips(r.get("fallback"))}</span></div>')
                if r.get("subscription") not in (None, "—"):
                    body.append(f'<div class="row"><span class="k">Abonnement</span><span class="chip sub">{esc(r["subscription"])}</span></div>')
            cards.append(f'<article class="card{" differs-card" if differs else ""}" data-differs="{int(differs)}" '
                         f'data-search="{esc(search.lower())}">' + "".join(body) + "</article>")
        icon, name = titles.get(t, ("•", t))
        sections.append(f'<section data-type="{t}"><h2>{icon} {name} <small>{len(items)}</small></h2>'
                        f'<div class="grid">{"".join(cards)}</div></section>')
    run = ctx.get("run") or {}
    when = run.get("finished_at") or run.get("started_at")
    when = when.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M UTC") if when else "?"
    counts = ctx.get("counts") or {}
    stats = " · ".join(f"{titles.get(k, ('', k))[1] or k} {counts[k]}" for k in order if k in counts)
    from walter_router.analysis.alerts import _board_fr   # 'arena:image_edit' -> 'Arena retouche d'image'
    def board(subject: str) -> str:
        bench, _, task = subject.partition(":")
        return _board_fr(f"{catalog.BOARDS.get(bench, bench)} {task}")
    down = "".join(f'<li>⚠️ {esc(board(d["subject"]))} — {esc((d["evidence"] or {}).get("reason", ""))}</li>'
                   for d in ctx.get("down") or [])
    n_diff = sum(1 for r in rs if r.get("differs") and r.get("chosen_by") == "toi")
    generated = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Walter Router — bibliothèque des modèles</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--muted:#6b7280;--line:#e5e7eb;--chip:#eef1f5;--star:#7c3aed;--calc:#2563eb;
--tier:#0d9488;--amber:#b45309;--amberbg:#fff7ed;--red:#b91c1c;--redbg:#fef2f2;--green:#047857;--greenbg:#ecfdf5}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f1115;--card:#171a21;--ink:#e8eaed;--muted:#9aa3af;--line:#262b35;
--chip:#222733;--amberbg:#2a1f10;--redbg:#2a1414;--greenbg:#0f241d}}}}
*{{box-sizing:border-box}}body{{margin:0;font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;
background:var(--bg);color:var(--ink)}}header{{padding:28px 24px 8px;max-width:1280px;margin:auto}}
h1{{margin:0 0 4px;font-size:24px}}.sub{{color:var(--muted)}}main{{max-width:1280px;margin:auto;padding:0 24px 48px}}
.tools{{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:16px 0}}
input[type=search]{{flex:1;min-width:220px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;
background:var(--card);color:var(--ink);font-size:15px}}label{{color:var(--muted);user-select:none}}
.tabs button{{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:7px 12px;border-radius:999px;
cursor:pointer;margin-right:4px}}.tabs button.on{{background:var(--ink);color:var(--bg)}}
h2{{font-size:18px;margin:28px 0 12px}}h2 small{{color:var(--muted);font-weight:400}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}}
.differs-card{{border-color:#f59e0b}}.task{{font-size:13px;color:var(--muted)}}.cat{{color:var(--ink);font-weight:600}}
.model{{font-size:18px;font-weight:650;margin:4px 0 6px}}.model.none{{color:var(--red)}}
.badge{{display:inline-block;font-size:12px;padding:2px 8px;border-radius:999px;color:#fff;margin-right:6px}}
.badge.star{{background:var(--star)}}.badge.calc{{background:var(--calc)}}.badge.tier{{background:var(--tier)}}
.score{{font-size:12px;color:var(--muted)}}.differs{{margin-top:8px;padding:6px 8px;border-radius:8px;background:var(--amberbg);
color:var(--amber);font-size:13px}}.warn{{margin-top:8px;padding:6px 8px;border-radius:8px;background:var(--redbg);color:var(--red);
font-size:13px}}.row{{display:flex;gap:10px;margin-top:10px;font-size:13px;align-items:baseline}}
.k{{flex:0 0 92px;color:var(--muted)}}.chip{{display:inline-block;background:var(--chip);border-radius:6px;padding:2px 7px;
margin:2px 0}}.chip.sub{{background:var(--greenbg);color:var(--green)}}.arrow{{color:var(--muted);margin:0 4px}}
.muted{{color:var(--muted)}}.down{{background:var(--redbg);color:var(--red);border-radius:12px;padding:10px 16px}}
.down ul{{margin:4px 0;padding-left:18px}}footer{{color:var(--muted);font-size:12px;margin-top:32px}}
.hide{{display:none!important}}
</style></head><body>
<header><h1>Walter Router — bibliothèque des modèles</h1>
<div class="sub">Dernier cycle : {esc(when)} · {ctx.get("tracked", 0)} modèles suivis ({esc(stats)}) ·
{n_diff} choix de ta part différents du n°1 mesuré</div></header>
<main>
{f'<div class="down"><b>Classements inaccessibles</b><ul>{down}</ul>Le router garde leur dernière lecture valable (21 jours).</div>' if down else ''}
<div class="tools"><input type="search" id="q" placeholder="Chercher un modèle, une tâche, un fournisseur…">
<label><input type="checkbox" id="diff"> seulement mes choix ≠ n°1</label></div>
<div class="tabs" id="tabs"><button class="on" data-t="">Tout</button>{"".join(f'<button data-t="{t}">{titles[t][0]} {titles[t][1]}</button>' for t in order if any(r["type"] == t for r in rs))}</div>
{"".join(sections)}
<footer>⭐ Ton choix = modèle que tu as fixé ; « ≠ n°1 » = le mieux classé est un autre (raison indiquée). 🤖 Calculé = meilleur
modèle exécutable selon les classements pondérés. 📐 Méthode des niveaux = L1/L2/L3 par ta méthode Pareto. Prix : texte en $
par million de tokens (entrée/sortie), image par image, vidéo par seconde (plage selon la résolution). Généré le {generated}.</footer>
</main>
<script>
const q=document.getElementById('q'),d=document.getElementById('diff');let tab='';
function f(){{const s=q.value.trim().toLowerCase();document.querySelectorAll('section').forEach(sec=>{{let n=0;
sec.querySelectorAll('.card').forEach(c=>{{const ok=(!s||c.dataset.search.includes(s))&&(!d.checked||c.dataset.differs==='1');
c.classList.toggle('hide',!ok);if(ok)n++}});sec.classList.toggle('hide',!n||(tab&&sec.dataset.type!==tab))}})}}
q.oninput=f;d.onchange=f;document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{{
document.querySelectorAll('#tabs button').forEach(x=>x.classList.remove('on'));b.classList.add('on');tab=b.dataset.t;f()}});
</script></body></html>"""


SITE = paths.SITE
CF = instance.host().get("cloudflare_cli", "")   # the instance's Cloudflare helper (publishing the page)


def publish(conn, deploy: bool = True) -> dict:
    """Rebuild the library page in the instance's build folder (host.json site_build) and deploy it to Cloudflare
    Pages (project walter-library, served only on the instance's library_domain behind Cloudflare Access; the
    functions shipped in site/functions refuse every other host). No domain or no Cloudflare helper = build only."""
    import subprocess
    import shutil
    from walter_router.interface import translate
    from walter_router.interface import page
    host = instance.host()
    build = instance.host_path("site_build") or SITE
    build.mkdir(parents=True, exist_ok=True)
    fill = {"__LIBRARY_HOST__": host.get("library_domain") or "", "__CONTROL_ORIGIN__": host.get("control_origin") or ""}
    shutil.rmtree(build / "functions", ignore_errors=True)
    for src in (SITE / "functions").rglob("*.js"):          # shipped functions, instance hosts filled in
        dest = build / src.relative_to(SITE)
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text()
        for k, v in fill.items():
            text = text.replace(k, v)
        dest.write_text(text)
    html = page.render(conn, rows(conn), _context(conn))   # French page; v2 (Muse Wonder) rejected 2026-10-14
    (build / "index.html").write_text(translate.to_english(html))   # English by default (2026-10-14)
    (build / "fr").mkdir(exist_ok=True)                                  # French page at /fr/, same layout
    (build / "fr" / "index.html").write_text(html)
    for old in ("v1", "en"):
        shutil.rmtree(build / old, ignore_errors=True)
    if not deploy or not CF or not fill["__LIBRARY_HOST__"]:
        return {"built": len(html), "deployed": False, "detail": [] if deploy is False else ["no library domain or Cloudflare helper for this instance"]}
    r = subprocess.run([CF, "--", "wrangler", "pages", "deploy", ".", "--project-name", "walter-library",
                        "--branch", "main", "--commit-dirty=true"], cwd=build, capture_output=True, text=True,
                       timeout=300)
    tail = [line for line in (r.stdout + r.stderr).splitlines() if line.strip()][-1:]
    return {"built": len(html), "deployed": r.returncode == 0, "detail": tail}

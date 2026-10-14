"""Library web page v2 — design by Meta Muse Wonder (Design Arena #1 for UI components), 2026-10-14.

Brief given to the model: everything Monsieur asked for (no AI look, professional, emojis with restraint, header =
title + run button + one status line, figures in the footer, levels beside the AA chart, Design Arena below, tabs with
counts, his choices that differ from #1 highlighted) plus the DOM hooks the JS and this generator rely on. Its CSS is
kept verbatim in library_v2.css (+ a small fix at the end); markup reproduced here from its output, fed by the same data
as v1 (library_page.py helpers).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import catalog, select as sel
from .library_page import EFFORT, LEVELS, ORIGIN, TAB_OF, TABS, _chart, _da, esc

CSS = Path(__file__).with_name("library_v2.css")
DEK = {"chat": "Modèle retenu par tâche, origine du choix, fournisseurs dans l’ordre et secours.",
       "image": "Génération et retouche d’image : modèle retenu, fournisseurs et secours.",
       "video": "Les lignes surlignées signalent ton choix lorsqu’il diffère du n°1 mesuré, avec la raison.",
       "audio": "Voix, conversation et musique.",
       "decisions": "Modèles de décision : routage de tes demandes et tri des entrées."}


def _route(text: str | None) -> str:
    if not text or text == "—":
        return '<span class="mute">—</span>'
    return '<span class="arr">→</span>'.join(f'<span class="nw">{esc(p.strip())}</span>' for p in text.split("→"))


def _table(rs: list[dict]) -> str:
    rows = []
    for r in rs:
        differs = bool(r.get("differs")) and r.get("chosen_by") == "toi"
        notes = (f'<div class="n-amber">≠ {esc(r["differs"])}</div>' if r.get("differs") else "") + \
                (f'<div class="n-red">{esc(r["warning"])}</div>' if r.get("warning") else "")
        search = " ".join(str(r.get(k) or "") for k in ("label", "category", "model", "providers", "fallback")).lower()
        cat = f'<div class="cat">{esc(r["category"])}</div>' if r.get("category") else ""
        mine = r.get("chosen_by") == "toi"
        origin = ORIGIN.get(r.get("chosen_by") or "", "Calculé")
        rows.append(f'<tr class="{"diff" if differs else ""}" data-search="{esc(search)}" data-differs="{int(differs)}">'
                    f'<td class="task">{esc(r["label"])}{cat}</td>'
                    f'<td class="model">{esc(r.get("model") or "Aucun modèle")}{notes}</td>'
                    f'<td class="origin{" mine" if mine else ""}">{origin}</td>'
                    f'<td class="num">{r["score"] if r.get("score") is not None else "—"}</td>'
                    f'<td class="route">{_route(r.get("providers"))}</td><td>{_route(r.get("fallback"))}</td>'
                    f'<td>{esc(r["subscription"]) if r.get("subscription") not in (None, "—") else ""}</td></tr>')
    return ('<div class="tw"><table class="lib"><thead><tr><th>Tâche</th><th>Modèle</th><th>Origine</th>'
            '<th class="num">Score</th><th>Fournisseurs (ordre, prix)</th><th>Secours</th><th>Abonnement</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def render(conn, rs: list[dict], ctx: dict) -> str:
    from .library import _name
    pts = sel.general_points(conn)
    run = conn.execute("select run_id from models.latest_run").fetchone()
    srows = list(conn.execute("""select level, model_id, variant, quality, real_cost from models.selection
                                 where run_id = %s and task = 'general' and level in ('frontier','L1','L2','L3')
                                 order by rank""", (run["run_id"],))) if run else []
    by = {(p["model_id"], p["variant"]): p for p in pts}

    def point(r):
        return by.get((r["model_id"], r["variant"])) or {"model_id": r["model_id"], "variant": r["variant"],
                                                         "name": _name(conn, r["model_id"]), "score": r["quality"],
                                                         "cost": r["real_cost"]}
    frontier = [point(r) for r in srows if r["level"] == "frontier" and r["real_cost"]]
    levels, lrows = {}, []
    for lvl in ("L1", "L2", "L3"):
        s = next((r for r in srows if r["level"] == lvl), None)
        card = next((r for r in rs if r["task"] == "general" and r.get("category") == LEVELS[lvl][0]), {})
        if not s:
            continue
        if s["real_cost"]:
            levels[lvl] = point(s)
        aa = (by.get((s["model_id"], s["variant"])) or {}).get("cost_aa")
        meta = ""
        if card.get("fallback") not in (None, "—"):
            meta += f'<div class="meta-line"><span class="rlab">Secours</span>{esc(card["fallback"])}</div>'
        if card.get("subscription") not in (None, "—"):
            meta += f'<div class="meta-line"><span class="rlab">Abonnement</span>{esc(card["subscription"])}</div>'
        lrows.append(
            f'<tr><td class="lvl"><span>{lvl}</span></td><td><div class="lname">{LEVELS[lvl][0]}</div></td>'
            f'<td class="model">{esc((card.get("model") or "—").split(" (")[0])}'
            f'<div class="effort">réflexion {EFFORT.get(s["variant"], s["variant"])}</div></td>'
            f'<td class="num">{f"{s["quality"]:.1f}".replace(".", ",")}</td>'
            f'<td class="num mute">{catalog.money(aa) + " $" if aa else "—"}</td>'
            f'<td class="num strong">{catalog.money(s["real_cost"]) + " $" if s["real_cost"] else "—"}</td></tr>'
            f'<tr class="sub"><td colspan="6"><p class="desc">{LEVELS[lvl][1]}</p><div class="route-line">'
            f'<span class="rlab">Fournisseurs</span>{_route(card.get("providers"))}</div>{meta}</td></tr>')
    da_rows = []
    for r in _da(conn, rs):
        lead = r["leader"]
        lead_txt = "" if not lead or lead["model_id"] == r.get("model_id") else \
            f'{esc(_name(conn, lead["model_id"]))} <span class="mute">({lead["score"]:.0f})</span>'
        rank = f'{r["rank"] or "—"}<span class="mute"> / {r["of"]}</span>'
        da_rows.append(f'<tr><td class="model-cell">{esc(r["label"])}</td><td class="model">{esc(r.get("model") or "—")}</td>'
                       f'<td class="num">{rank}</td><td class="num">{f"{r["elo"]:.0f}" if r.get("elo") else "—"}</td>'
                       f'<td class="amber">{lead_txt}</td><td class="route">{_route(r.get("providers"))}</td></tr>')
    panes = {k: [r for r in rs if r["task"] != "general" and TAB_OF.get(r["type"]) == k] for k, _, _ in TABS}
    run_info = ctx.get("run") or {}
    when = run_info.get("finished_at") or run_info.get("started_at")
    when = when.astimezone(timezone.utc).strftime("%d/%m/%Y, %H:%M UTC") if when else "?"
    counts = ctx.get("counts") or {}
    n_diff = sum(1 for r in rs if r.get("differs") and r.get("chosen_by") == "toi")
    figs = [("Modèles suivis", ctx.get("tracked", 0)), ("Texte", counts.get("chat", 0)), ("Image", counts.get("image", 0)),
            ("Vidéo", counts.get("video", 0)), ("Audio & musique", counts.get("audio", 0) + counts.get("music", 0))]
    tabs = "".join(f'<a href="#{k}" data-tab="{k}"{" class=on" if k == "home" else ""}><span class="ic">{i}</span>{n}'
                   + (f'<span class="ct">{len(panes[k])}</span>' if k != "home" else "") + "</a>" for k, i, n in TABS)
    sections = "".join(f'<section class="pane" data-pane="{k}" hidden><div class="block-flush"><h2>{i} {n}</h2>'
                       f'<p class="dek">{DEK.get(k, "")}</p>{_table(panes[k])}</div></section>'
                       for k, i, n in TABS if k != "home")
    generated = datetime.now(timezone.utc).strftime("%d/%m/%Y, %H:%M UTC")
    script = (Path(__file__).with_name("library_v2.js")).read_text()
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Bibliothèque des modèles — Walter Router</title>
<style>{CSS.read_text()}</style></head><body>
<header><div class="wrap header-in">
<div class="brand"><div class="mark" aria-hidden="true">W</div><div><p class="kicker">Walter Router — privé</p><h1>Bibliothèque des modèles</h1></div></div>
<div class="runbox"><div id="runstate" class="mute" role="status" aria-live="polite"></div><button id="runbtn" type="button"><span class="play" aria-hidden="true">▶</span> Lancer le cycle complet</button></div>
</div></header>
<nav aria-label="Catégories"><div class="wrap navin"><div class="tabs" role="tablist">{tabs}</div>
<div class="tools"><div class="search"><input type="search" id="q" placeholder="Rechercher un modèle, une tâche…" aria-label="Rechercher"></div>
<label class="f"><input type="checkbox" id="diff"> Mes choix ≠ n°1 <span class="cnt">({n_diff})</span></label></div></div></nav>
<main class="wrap">
<section class="pane" data-pane="home"><div class="split">
<div class="panel"><h2>🧠 Niveaux de réflexion</h2><p class="dek">Optimum de Pareto calculé par ta méthode sur la frontière AA.</p>
<div class="tw"><table class="levels"><thead><tr><th colspan="2">Niveau</th><th>Modèle</th><th class="num">Indice AA</th>
<th class="num" title="Prix de référence publié par Artificial Analysis">Coût AA officiel</th>
<th class="num" title="Recalculé avec le prix du fournisseur utilisé">Coût réel</th></tr></thead><tbody>{"".join(lrows)}</tbody></table></div></div>
<div class="panel"><h2>📈 Indice d’intelligence et coût par tâche</h2><p class="dek">{len(pts)} combinaisons modèle × niveau de réflexion exécutables.</p>
<div class="chart-tools"><div class="seg" id="costseg" role="group" aria-label="Base de coût"><button data-cost="cost" class="on">Coût réel</button><button data-cost="cost_aa">Coût AA officiel</button></div><span class="chart-note">Échelle log.</span></div>
{_chart(pts, frontier, levels)}{_chart(pts, frontier, levels, "cost_aa")}</div></div>
<div class="block"><div class="section-head"><div><h2>🎨 Spécialisations Design Arena</h2><p class="dek">Rang du modèle retenu sur le classement Design Arena de chaque tâche.</p></div></div>
<div class="tw"><table class="data"><thead><tr><th>Tâche</th><th>Modèle retenu</th><th class="num">Rang</th><th class="num">Score</th><th>N°1 Design Arena, si différent</th><th>Fournisseurs</th></tr></thead>
<tbody>{"".join(da_rows)}</tbody></table></div></div>
</section>
{sections}
</main>
<footer><div class="wrap footer-in">
<div class="foot-figs">{"".join(f"<span>{esc(lbl)} <b>{v}</b></span>" for lbl, v in figs)}<span>Classements recalculés le {esc(when)}</span><span>Cycle complet automatique toutes les 48 heures</span></div>
<p>Origine : « Ton choix » = modèle fixé par toi ; « Calculé » = meilleur modèle exécutable selon les classements pondérés ; « Méthode Pareto » = niveaux L1, L2, L3. Une ligne surlignée signale un choix de ta part différent du n°1 mesuré, avec la raison. Page republiée après chacune de tes réponses.</p>
<p>Prix : texte en dollars par million de tokens (entrée/sortie), image par image, vidéo par seconde (plage selon la résolution) ; « estimé » lorsque le fournisseur facture au token. Design : Meta Muse Wonder. Page générée le {generated}.</p>
</div></footer>
<script>{script}</script></body></html>"""

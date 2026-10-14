"""Library web page (v3, Monsieur 2026-10-14: « le design fait trop IA, pas pro »).

Editorial / market-terminal posture: paper background, black ink, one accent, hairline rules, dense tables with
tabular figures, no emoji, no gradient, no pill badges. Home: the three reasoning levels (Pareto optimum of
Monsieur's method) beside the AA chart, then the Design Arena specialisations. Tabs: Texte, Image, Vidéo,
Audio & musique, Décision. Self-contained HTML; chart in inline SVG with hover. Chart palette validated with the
dataviz validator: light #2a78d6 / #eb6834 on #ffffff, dark #3987e5 / #d95926 on #141414.
"""
from __future__ import annotations

import html
import json
import math
from datetime import datetime, timezone

from . import catalog, select as sel

esc = html.escape
TABS = [("home", "Vue d'ensemble"), ("chat", "Texte"), ("image", "Image"), ("video", "Vidéo"),
        ("audio", "Audio & musique"), ("decisions", "Décision")]
TAB_OF = {"chat": "chat", "image": "image", "video": "video", "audio": "audio", "music": "audio", "decisions": "decisions"}
LEVELS = {"L1": ("Économique", "Quotidien : réponses courtes, résumés, petites rédactions"),
          "L2": ("Intermédiaire", "Analyse en plusieurs étapes, comparaison, rédaction soignée"),
          "L3": ("Haut de gamme", "Raisonnement profond, synthèse, enjeu important")}
EFFORT = {"low": "faible", "medium": "moyenne", "high": "élevée", "xhigh": "très élevée", "max": "maximale"}
ORIGIN = {"toi": "Ton choix", "calcul": "Calculé", "méthode des niveaux": "Méthode Pareto"}


def _route(text: str | None) -> str:
    if not text or text == "—":
        return '<span class="mute">—</span>'
    return '<span class="arr"> → </span>'.join(f'<span class="nw">{esc(p.strip())}</span>' for p in text.split("→"))


def _chart(points: list[dict], frontier: list[dict], levels: dict[str, dict]) -> str:
    if not points:
        return '<p class="mute">Pas de données AA.</p>'
    W, H, L, R, T, B = 680, 430, 44, 16, 14, 40
    lo = math.floor(math.log10(min(p["cost"] for p in points)))
    hi = math.ceil(math.log10(max(p["cost"] for p in points)))
    ys = [p["score"] for p in points]
    ylo, yhi = 10 * math.floor(min(ys) / 10), 10 * math.ceil(max(ys) / 10)
    X = lambda c: L + (math.log10(c) - lo) / (hi - lo) * (W - L - R)  # noqa: E731
    Y = lambda s: T + (yhi - s) / (yhi - ylo) * (H - T - B)  # noqa: E731
    g = []
    for e in range(lo, hi + 1):
        x = X(10 ** e)
        g.append(f'<line class="gl" x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{H - B}"/>'
                 f'<text class="tk" x="{x:.1f}" y="{H - B + 16}" text-anchor="middle">{catalog.money(10 ** e)} $</text>')
    for s in range(int(ylo), int(yhi) + 1, 10):
        y = Y(s)
        g.append(f'<line class="gl" x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}"/>'
                 f'<text class="tk" x="{L - 8}" y="{y + 4:.1f}" text-anchor="end">{s}</text>')
    g.append(f'<line class="ax" x1="{L}" y1="{H - B}" x2="{W - R}" y2="{H - B}"/>')

    def tip(p: dict) -> str:
        return esc(json.dumps({"n": p["name"], "s": round(p["score"], 1), "c": catalog.money(p["cost"]),
                               "p": catalog.PROVIDERS.get(p.get("provider") or "", p.get("provider") or "")},
                              ensure_ascii=False))
    on_f = {(f["model_id"], f["variant"]) for f in frontier}
    g += [f'<circle class="pt" cx="{X(p["cost"]):.1f}" cy="{Y(p["score"]):.1f}" r="3" data-tip="{tip(p)}"/>'
          for p in points if (p["model_id"], p["variant"]) not in on_f]
    fr = sorted(frontier, key=lambda f: f["cost"])
    if fr:
        g.append('<polyline class="fr" points="' + " ".join(f'{X(f["cost"]):.1f},{Y(f["score"]):.1f}' for f in fr) + '"/>')
        g += [f'<circle class="fp" cx="{X(f["cost"]):.1f}" cy="{Y(f["score"]):.1f}" r="4" data-tip="{tip(f)}"/>' for f in fr]
    for lvl, p in levels.items():
        x, y = X(p["cost"]), Y(p["score"])
        g.append(f'<circle class="lv" cx="{x:.1f}" cy="{y:.1f}" r="5.5" data-tip="{tip(p)}"/>'
                 f'<text class="ll" x="{x - 9:.1f}" y="{y - 9:.1f}" text-anchor="end">{lvl}</text>')
    return (f'<figure class="chart"><svg viewBox="0 0 {W} {H}" role="img" aria-label="Indice AA en fonction du coût '
            f'réel par tâche">{"".join(g)}</svg><figcaption><span><i class="k1"></i>Modèles exécutables</span>'
            f'<span><i class="k2"></i>Frontière de Pareto</span><span><i class="k3"></i>Niveaux retenus</span>'
            f'<span class="mute">Abscisse : coût réel par tâche AA, échelle logarithmique</span></figcaption>'
            f'<div class="tip" id="tip"></div></figure>')


def _da(conn, rs: list[dict]) -> list[dict]:
    snaps = sel.latest_snapshots(conn)
    out = []
    for t in conn.execute("""select tb.task, tb.benchmark, tb.bench_task from models.task_benchmarks tb
                             where tb.benchmark in ('da_models', 'da_agents') order by tb.weight desc""").fetchall():
        if any(o["task"] == t["task"] for o in out):
            continue
        row = next((r for r in rs if r["task"] == t["task"]), None)
        sid = sel.board_snapshot(conn, snaps, t["benchmark"], t["bench_task"])
        if not row or not sid:
            continue
        board = list(conn.execute("""select model_id, max(score) as score from models.benchmarks where snapshot_id = %s
                                     and benchmark = %s and task = %s group by 1 order by 2 desc""",
                                  (sid, t["benchmark"], t["bench_task"])))
        rank = next((i + 1 for i, b in enumerate(board) if b["model_id"] == row.get("model_id")), None)
        elo = next((b["score"] for b in board if b["model_id"] == row.get("model_id")), None)
        out.append({**row, "rank": rank, "elo": elo, "of": len(board), "leader": board[0] if board else None})
    return sorted(out, key=lambda r: r["label"])


def _table(rs: list[dict]) -> str:
    head = ('<thead><tr><th>Tâche</th><th>Modèle</th><th>Origine</th><th class="num">Score</th>'
            '<th>Fournisseurs (ordre, prix)</th><th>Secours</th><th>Abonnement</th></tr></thead>')
    body, last = [], None
    for r in rs:
        differs = bool(r.get("differs")) and r.get("chosen_by") == "toi"
        task = esc(r["label"]) if r["label"] != last else ""
        last = r["label"]
        cat = f'<div class="cat">{esc(r["category"])}</div>' if r.get("category") else ""
        notes = ""
        if r.get("differs"):
            notes += f'<div class="n-amber">≠ {esc(r["differs"])}</div>'
        if r.get("warning"):
            notes += f'<div class="n-red">{esc(r["warning"])}</div>'
        search = " ".join(str(r.get(k) or "") for k in ("label", "category", "model", "providers", "fallback")).lower()
        score = r.get("score") if r.get("score") is not None else "—"
        origin = ORIGIN.get(r.get("chosen_by") or "", "Calculé")
        body.append(
            f'<tr class="{"diff" if differs else ""}" data-search="{esc(search)}" data-differs="{int(differs)}">'
            f'<td class="task">{task}{cat}</td>'
            f'<td class="model">{esc(r.get("model") or "Aucun modèle")}{notes}</td>'
            f'<td class="origin{" mine" if r.get("chosen_by") == "toi" else ""}">{origin}</td>'
            f'<td class="num">{score}</td><td class="route">{_route(r.get("providers"))}</td>'
            f'<td>{_route(r.get("fallback"))}</td>'
            f'<td>{esc(r["subscription"]) if r.get("subscription") not in (None, "—") else ""}</td></tr>')
    return f'<div class="tw"><table class="lib">{head}<tbody>{"".join(body)}</tbody></table></div>'


def render(conn, rs: list[dict], ctx: dict) -> str:
    from .library import _name
    from .alerts import _board_fr
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
        effort = EFFORT.get(s["variant"], s["variant"])
        sub = card.get("subscription")
        cost = f'{catalog.money(s["real_cost"])} $' if s["real_cost"] else "—"
        lrows.append(
            f'<tr><td class="lvl">{lvl}</td><td><div class="lname">{LEVELS[lvl][0]}</div>'
            f'<div class="mute small">{LEVELS[lvl][1]}</div></td>'
            f'<td class="model">{esc((card.get("model") or "—").split(" (")[0])}<div class="mute small">réflexion {effort}</div></td>'
            f'<td class="num">{f"{s["quality"]:.1f}".replace(".", ",")}</td><td class="num">{cost}</td></tr>'
            f'<tr class="sub"><td></td><td colspan="4"><span class="mute">Fournisseurs</span> {_route(card.get("providers"))}'
            + (f'<span class="mute sep2">Secours</span> {esc(card["fallback"])}' if card.get("fallback") not in (None, "—") else "")
            + (f'<span class="mute sep2">Abonnement</span> {esc(sub)}' if sub not in (None, "—") else "") + "</td></tr>")
    da_rows = []
    for r in _da(conn, rs):
        lead = r["leader"]
        lead_txt = "" if not lead or lead["model_id"] == r.get("model_id") else \
            f'{esc(_name(conn, lead["model_id"]))} <span class="mute">({lead["score"]:.0f})</span>'
        elo = f'{r["elo"]:.0f}' if r.get("elo") else "—"
        da_rows.append(f'<tr><td>{esc(r["label"])}</td><td class="model">{esc(r.get("model") or "—")}</td>'
                       f'<td class="num">{r["rank"] or "—"}<span class="mute"> / {r["of"]}</span></td>'
                       f'<td class="num">{elo}</td>'
                       f'<td class="amber">{lead_txt}</td><td class="route">{_route(r.get("providers"))}</td></tr>')
    panes = {k: [r for r in rs if r["task"] != "general" and TAB_OF.get(r["type"]) == k] for k, _ in TABS}
    run_info = ctx.get("run") or {}
    when = run_info.get("finished_at") or run_info.get("started_at")
    when = when.astimezone(timezone.utc).strftime("%d/%m/%Y, %H:%M UTC") if when else "?"
    counts = ctx.get("counts") or {}
    n_diff = sum(1 for r in rs if r.get("differs") and r.get("chosen_by") == "toi")
    figures = [("Modèles suivis", ctx.get("tracked", 0)), ("Texte", counts.get("chat", 0)),
               ("Image", counts.get("image", 0)), ("Vidéo", counts.get("video", 0)),
               ("Audio & musique", counts.get("audio", 0) + counts.get("music", 0)), ("Tes choix ≠ n°1", n_diff)]
    down = ctx.get("down") or []
    down_txt = "; ".join(_board_fr(f'{catalog.BOARDS.get(d["subject"].split(":")[0], d["subject"].split(":")[0])} '
                                   f'{d["subject"].partition(":")[2]}') for d in down)
    nav = "".join(f'<a href="#{k}" data-tab="{k}"{" class=on" if k == "home" else ""}>{n}'
                  + (f'<sup>{len(panes[k])}</sup>' if k != "home" else "") + "</a>" for k, n in TABS)
    tab_html = "".join(f'<section class="pane" data-pane="{k}" hidden><h2>{n}</h2>{_table(panes[k])}</section>'
                       for k, n in TABS if k != "home")
    generated = datetime.now(timezone.utc).strftime("%d/%m/%Y, %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Bibliothèque des modèles — Walter Router</title>
<style>
:root{{--bg:#fbfbf9;--paper:#ffffff;--ink:#141414;--ink2:#3d3d3a;--mute:#73736e;--rule:#e3e3de;--rule2:#c9c9c2;
--accent:#1d4ed8;--amber:#8a5300;--amberbg:#fdf6e7;--red:#b42318;--c1:#2a78d6;--c2:#eb6834;--pt:#b9b9b2;--surface:#ffffff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f0f0f;--paper:#141414;--ink:#ececea;--ink2:#c9c9c4;--mute:#8d8d87;
--rule:#262624;--rule2:#3a3a37;--accent:#7aa2ff;--amber:#e3a63b;--amberbg:#221a0c;--red:#f0786b;--c1:#3987e5;--c2:#d95926;
--pt:#4a4a46;--surface:#141414}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 "Helvetica Neue",Helvetica,Arial,system-ui,sans-serif;
-webkit-font-smoothing:antialiased;font-feature-settings:"tnum" 1,"lnum" 1}}
.wrap{{max-width:1240px;margin:0 auto;padding:0 32px}}
header{{padding:36px 0 0}}.kicker{{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute)}}
h1{{font:600 30px/1.15 Georgia,"Times New Roman",serif;letter-spacing:-.01em;margin:6px 0 4px}}
.meta{{color:var(--mute);font-size:13px}}
.figures{{display:grid;grid-template-columns:repeat(6,1fr);border-top:2px solid var(--ink);border-bottom:1px solid var(--rule);
margin-top:22px}}.figures div{{padding:12px 14px 12px 0}}.figures div+div{{border-left:1px solid var(--rule);padding-left:14px}}
.figures b{{display:block;font-size:22px;font-weight:600;letter-spacing:-.01em}}.figures span{{color:var(--mute);font-size:12px}}
.figures .hl b{{color:var(--amber)}}
nav{{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--rule2)}}
.navin{{display:flex;align-items:center;gap:26px;overflow-x:auto}}
nav a{{color:var(--ink2);text-decoration:none;padding:14px 0 12px;border-bottom:2px solid transparent;white-space:nowrap;font-size:13.5px}}
nav a:hover{{color:var(--ink)}}nav a.on{{color:var(--ink);border-bottom-color:var(--ink);font-weight:600}}
nav sup{{color:var(--mute);font-size:10px;margin-left:3px}}
.tools{{margin-left:auto;display:flex;gap:16px;align-items:center}}
input[type=search]{{border:0;border-bottom:1px solid var(--rule2);background:transparent;color:var(--ink);padding:6px 2px;
width:240px;font:inherit;outline:none}}input[type=search]:focus{{border-bottom-color:var(--ink)}}
label.f{{font-size:13px;color:var(--ink2);white-space:nowrap}}
main{{padding:28px 0 64px}}
h2{{font:600 19px/1.3 Georgia,"Times New Roman",serif;margin:0 0 2px}}.dek{{color:var(--mute);margin:0 0 14px;font-size:13px}}
.notice{{color:var(--red);font-size:13px;margin:0 0 22px;padding:8px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}}
.split{{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,6fr);gap:40px}}
table{{width:100%;border-collapse:collapse}}th{{text-align:left;font-weight:600;font-size:11px;letter-spacing:.06em;
text-transform:uppercase;color:var(--mute);padding:8px 10px 8px 0;border-bottom:1px solid var(--ink)}}
td{{padding:10px 10px 10px 0;border-bottom:1px solid var(--rule);vertical-align:top}}
.num{{text-align:right;white-space:nowrap}}th.num{{text-align:right}}
.levels td{{border-bottom:0;padding-bottom:2px}}.levels tr.sub td{{border-bottom:1px solid var(--rule);padding-top:0;padding-bottom:12px;
font-size:12.5px;color:var(--ink2)}}.lvl{{font-weight:700;font-size:15px;width:34px}}.lname{{font-weight:600}}
.model{{font-weight:600}}.levels .model{{white-space:nowrap}}.small{{font-size:12px;font-weight:400}}.mute{{color:var(--mute)}}.sep2{{margin-left:14px}}
.arr{{color:var(--mute)}}.nw{{white-space:nowrap}}.amber{{color:var(--amber);font-size:12.5px}}
.lib td.task{{width:17%;font-weight:600}}.lib .cat{{font-weight:400;color:var(--ink2)}}.lib td.route{{font-size:12.5px}}
.lib td{{font-size:13px}}.origin{{color:var(--mute);white-space:nowrap}}.origin.mine{{color:var(--ink);font-weight:600}}
.n-amber{{font-weight:400;font-size:12px;color:var(--amber);margin-top:3px}}.n-red{{font-weight:400;font-size:12px;color:var(--red);margin-top:3px}}
tr.diff td{{background:var(--amberbg)}}.tw{{overflow-x:auto}}
.chart{{margin:0;position:relative}}.chart svg{{width:100%;height:auto;display:block}}
.gl{{stroke:var(--rule);stroke-width:1}}.ax{{stroke:var(--ink);stroke-width:1}}.tk{{fill:var(--mute);font-size:11px}}
.pt{{fill:var(--pt)}}.fr{{fill:none;stroke:var(--c1);stroke-width:2}}.fp{{fill:var(--c1);stroke:var(--surface);stroke-width:2}}
.lv{{fill:var(--c2);stroke:var(--surface);stroke-width:2}}.ll{{fill:var(--ink);font-size:12px;font-weight:700}}
.pt,.fp,.lv{{cursor:crosshair}}
figcaption{{display:flex;flex-wrap:wrap;gap:16px;font-size:12px;color:var(--ink2);margin-top:6px}}
figcaption i{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}}
.k1{{background:var(--pt)}}.k2{{background:var(--c1)}}.k3{{background:var(--c2)}}
.tip{{position:absolute;display:none;pointer-events:none;background:var(--paper);border:1px solid var(--rule2);padding:6px 9px;
font-size:12px;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
.block{{margin-top:44px}}[hidden]{{display:none!important}}.hide{{display:none!important}}
footer{{border-top:1px solid var(--rule2);color:var(--mute);font-size:12px;padding:16px 0 40px;line-height:1.6}}
@media (max-width:980px){{.split{{grid-template-columns:1fr}}.figures{{grid-template-columns:repeat(3,1fr)}}
.figures div:nth-child(4){{border-left:0;padding-left:0}}}}
@media (max-width:600px){{.wrap{{padding:0 16px}}.figures{{grid-template-columns:repeat(2,1fr)}}.tools{{display:none}}
.figures div{{border-left:0!important;padding-left:0!important}}}}
</style></head><body>
<div class="wrap"><header><div class="kicker">Walter Router</div><h1>Bibliothèque des modèles</h1>
<div class="meta">Dernier cycle : {esc(when)}. Mise à jour toutes les 48 heures et après chacune de tes réponses.</div>
<div class="figures">{"".join(f'<div class="{"hl" if lbl.startswith("Tes") else ""}"><b>{v}</b><span>{esc(lbl)}</span></div>' for lbl, v in figures)}</div>
</header></div>
<nav><div class="wrap navin">{nav}<div class="tools"><input type="search" id="q" placeholder="Rechercher">
<label class="f"><input type="checkbox" id="diff"> Mes choix ≠ n°1</label></div></div></nav>
<main class="wrap">
{f'<p class="notice">Classement inaccessible : {esc(down_txt)}. Le router conserve sa dernière lecture valable pendant 21 jours.</p>' if down else ''}
<section class="pane" data-pane="home">
<div class="split"><div><h2>Niveaux de réflexion</h2><p class="dek">Optimum de Pareto calculé par ta méthode sur la frontière AA</p>
<table class="levels"><colgroup><col style="width:34px"><col><col style="width:30%"><col style="width:76px"><col style="width:96px"></colgroup><thead><tr><th></th><th>Niveau</th><th>Modèle</th><th class="num">Indice AA</th><th class="num">Coût / tâche</th></tr></thead>
<tbody>{"".join(lrows)}</tbody></table></div>
<div><h2>Indice d'intelligence et coût réel</h2><p class="dek">{len(pts)} combinaisons modèle × niveau de réflexion exécutables</p>{_chart(pts, frontier, levels)}</div></div>
<div class="block"><h2>Spécialisations Design Arena</h2><p class="dek">Rang du modèle retenu sur le classement Design Arena de chaque tâche</p>
<div class="tw"><table><thead><tr><th>Tâche</th><th>Modèle retenu</th><th class="num">Rang</th><th class="num">Score</th>
<th>N°1 Design Arena, si différent</th><th>Fournisseurs</th></tr></thead><tbody>{"".join(da_rows)}</tbody></table></div></div>
</section>
{tab_html}
</main>
<div class="wrap"><footer>Origine : « Ton choix » = modèle fixé par toi ; « Calculé » = meilleur modèle exécutable selon les classements
pondérés ; « Méthode Pareto » = niveaux L1, L2, L3. Une ligne surlignée signale un choix de ta part différent du n°1 mesuré, avec la raison.
Prix : texte en dollars par million de tokens (entrée/sortie), image par image, vidéo par seconde (plage selon la résolution) ;
« estimé » lorsque le fournisseur facture au token. Page générée le {generated}.</footer></div>
<script>
const links=document.querySelectorAll('nav a'),panes=document.querySelectorAll('.pane'),q=document.getElementById('q'),
d=document.getElementById('diff');let cur='home';
function show(t){{cur=t;links.forEach(a=>a.classList.toggle('on',a.dataset.tab===t));panes.forEach(p=>p.hidden=p.dataset.pane!==t);filter()}}
function filter(){{const s=(q.value||'').trim().toLowerCase();if((s||d.checked)&&cur==='home'){{show(d.checked?'video':'chat');return}}
document.querySelectorAll('tbody tr[data-search]').forEach(r=>r.classList.toggle('hide',!((!s||r.dataset.search.includes(s))&&(!d.checked||r.dataset.differs==='1'))))}}
links.forEach(a=>a.onclick=e=>{{e.preventDefault();show(a.dataset.tab);history.replaceState(null,'','#'+a.dataset.tab)}});
q.oninput=filter;d.onchange=filter;
const tip=document.getElementById('tip');document.querySelectorAll('[data-tip]').forEach(el=>{{
el.addEventListener('mouseenter',()=>{{const o=JSON.parse(el.dataset.tip);tip.innerHTML='<b>'+o.n+'</b><br>Indice '+o.s+' · '+o.c+' $ par tâche'+(o.p?' · '+o.p:'');tip.style.display='block'}});
el.addEventListener('mousemove',e=>{{const r=tip.parentElement.getBoundingClientRect();tip.style.left=(e.clientX-r.left+12)+'px';tip.style.top=(e.clientY-r.top-8)+'px'}});
el.addEventListener('mouseleave',()=>tip.style.display='none')}});
show((location.hash||'#home').slice(1)||'home');
</script></body></html>"""

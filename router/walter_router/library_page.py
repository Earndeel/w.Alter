"""Library web page (v2, Monsieur 2026-10-14: « fais-moi un meilleur design »).

Home: 🧠 the three reasoning levels (Pareto optimum of his method) beside the AA chart (Intelligence Index vs real
cost per task, frontier, L1/L2/L3), then the Design Arena specialisations. Tabs: Texte, Image, Vidéo,
Audio & Musique, Décision. One self-contained HTML file (no external asset), dark theme, chart in inline SVG with
hover tooltips. Chart palette validated with the dataviz validator (dark, surface #12141b): #3987e5 / #d95926.
"""
from __future__ import annotations

import html
import json
import math
from datetime import datetime, timezone

from . import catalog, select as sel

esc = html.escape
TABS = [("home", "🏠", "Accueil"), ("chat", "💬", "Texte"), ("image", "🖼️", "Image"), ("video", "🎬", "Vidéo"),
        ("audio", "🎧", "Audio & Musique"), ("decisions", "🧭", "Décision")]
TAB_OF = {"chat": "chat", "image": "image", "video": "video", "audio": "audio", "music": "audio", "decisions": "decisions"}
LEVELS = {"L1": ("Économique", "Le quotidien : réponses courtes, résumés, petites rédactions"),
          "L2": ("Intermédiaire", "Analyse en plusieurs étapes, comparaison, rédaction soignée"),
          "L3": ("Haut de gamme", "Raisonnement profond, synthèse de recherche, enjeu important")}
EFFORT = {"low": "faible", "medium": "moyenne", "high": "élevée", "xhigh": "très élevée", "max": "maximale"}
BADGE = {"toi": ("star", "⭐ Ton choix"), "calcul": ("calc", "🤖 Calculé"),
         "méthode des niveaux": ("tier", "📐 Méthode Pareto")}


def _chips(text: str | None) -> str:
    if not text or text == "—":
        return '<span class="muted">—</span>'
    parts = [p.strip() for p in text.split("→")]
    return '<span class="sep">›</span>'.join(f'<span class="chip">{esc(p)}</span>' for p in parts)


def _card(r: dict, compact: bool = False) -> str:
    cls, label = BADGE.get(r.get("chosen_by") or "", BADGE["calcul"])
    differs = bool(r.get("differs")) and r.get("chosen_by") == "toi"
    search = " ".join(str(r.get(k) or "") for k in ("label", "category", "model", "providers", "fallback")).lower()
    head = (f'<div class="eyebrow">{esc(r["label"])}'
            + (f'<span class="dot">•</span><b>{esc(r["category"])}</b>' if r.get("category") else "") + "</div>")
    if not r.get("model"):
        return (f'<article class="card empty" data-search="{esc(search)}" data-differs="0">{head}'
                f'<div class="model">Aucun modèle</div><div class="note warn">⚠️ {esc(r.get("warning") or "")}</div></article>')
    score = (f'<span class="score">{r["score"]}<small>/100</small></span>'
             if r.get("score") is not None and r.get("chosen_by") != "méthode des niveaux" else "")
    body = [head, f'<div class="title"><div class="model">{esc(r["model"])}</div>{score}</div>',
            f'<span class="badge {cls}">{label}</span>']
    if r.get("differs"):
        body.append(f'<div class="note amber">≠ {esc(r["differs"])}</div>')
    if r.get("warning"):
        body.append(f'<div class="note warn">⚠️ {esc(r["warning"])}</div>')
    body.append('<dl>'
                f'<dt>Fournisseurs</dt><dd>{_chips(r.get("providers"))}</dd>'
                f'<dt>Secours</dt><dd>{_chips(r.get("fallback"))}</dd>'
                + (f'<dt>Abonnement</dt><dd><span class="chip sub">{esc(r["subscription"])}</span></dd>'
                   if r.get("subscription") not in (None, "—") else "") + '</dl>')
    return (f'<article class="card{" differs" if differs else ""}" data-search="{esc(search)}" '
            f'data-differs="{int(differs)}">' + "".join(body) + "</article>")


def _chart(points: list[dict], frontier: list[dict], levels: dict[str, dict]) -> str:
    """Scatter: AA Intelligence Index (y) vs real cost per AA task (x, log), frontier line, L1/L2/L3 labelled."""
    if not points:
        return '<div class="muted">Pas de données AA.</div>'
    W, H, L, R, T, B = 640, 470, 52, 18, 16, 46
    xs = [p["cost"] for p in points]
    lo, hi = math.log10(min(xs)), math.log10(max(xs))
    lo, hi = math.floor(lo), math.ceil(hi)
    ys = [p["score"] for p in points]
    ylo, yhi = 5 * math.floor(min(ys) / 5), 5 * math.ceil(max(ys) / 5)
    X = lambda c: L + (math.log10(c) - lo) / (hi - lo) * (W - L - R)  # noqa: E731
    Y = lambda s: T + (yhi - s) / (yhi - ylo) * (H - T - B)  # noqa: E731
    g = []
    for e in range(lo, hi + 1):                                          # x grid: decades
        x = X(10 ** e)
        g.append(f'<line class="gl" x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{H - B}"/>'
                 f'<text class="tick" x="{x:.1f}" y="{H - B + 18}" text-anchor="middle">{catalog.money(10 ** e)} $</text>')
    for s in range(int(ylo), int(yhi) + 1, 10):
        y = Y(s)
        g.append(f'<line class="gl" x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}"/>'
                 f'<text class="tick" x="{L - 8}" y="{y + 4:.1f}" text-anchor="end">{s}</text>')
    g.append(f'<text class="axis" x="{(L + W - R) / 2:.0f}" y="{H - 6}" text-anchor="middle">Coût réel par tâche AA '
             f'(échelle log)</text><text class="axis" transform="translate(14 {(T + H - B) / 2:.0f}) rotate(-90)" '
             f'text-anchor="middle">AA Intelligence Index</text>')

    def tip(p: dict) -> str:
        return esc(json.dumps({"n": p["name"], "s": round(p["score"], 1), "c": catalog.money(p["cost"]),
                               "p": catalog.PROVIDERS.get(p.get("provider") or "", p.get("provider") or "")},
                              ensure_ascii=False))
    on_f = {(f["model_id"], f["variant"]) for f in frontier}
    g += [f'<circle class="pt" cx="{X(p["cost"]):.1f}" cy="{Y(p["score"]):.1f}" r="3.5" data-tip="{tip(p)}"/>'
          for p in points if (p["model_id"], p["variant"]) not in on_f]
    fr = sorted(frontier, key=lambda f: f["cost"])
    if fr:
        g.append('<polyline class="frontier" points="' + " ".join(f'{X(f["cost"]):.1f},{Y(f["score"]):.1f}' for f in fr)
                 + '"/>')
        g += [f'<circle class="fpt" cx="{X(f["cost"]):.1f}" cy="{Y(f["score"]):.1f}" r="4.5" data-tip="{tip(f)}"/>'
              for f in fr]
    for lvl, p in levels.items():
        x, y = X(p["cost"]), Y(p["score"])
        g.append(f'<circle class="lvl" cx="{x:.1f}" cy="{y:.1f}" r="7" data-tip="{tip(p)}"/>'
                 f'<text class="lvl-label" x="{x - 10:.1f}" y="{y - 12:.1f}" text-anchor="end">{lvl} · '
                 f'{esc(p["short"])}</text>')
    legend = ('<div class="legend"><span><i class="k-pt"></i>Modèles exécutables</span>'
              '<span><i class="k-fr"></i>Frontière de Pareto</span><span><i class="k-lvl"></i>Tes 3 niveaux</span></div>')
    return (f'<div class="chart"><svg viewBox="0 0 {W} {H}" role="img" aria-label="AA Intelligence Index en fonction '
            f'du coût par tâche">{"".join(g)}</svg>{legend}<div class="tip" id="tip"></div></div>')


def _da_specialisations(conn, rs: list[dict]) -> list[dict]:
    """Tasks ranked by Design Arena boards: chosen model, its Elo and rank on the task's DA board, the DA leader."""
    snaps = sel.latest_snapshots(conn)
    out = []
    for t in conn.execute("""select tb.task, tb.benchmark, tb.bench_task, t.label from models.task_benchmarks tb
                             join models.tasks t using (task) where tb.benchmark in ('da_models', 'da_agents')
                             order by tb.weight desc""").fetchall():
        if any(o["task"] == t["task"] for o in out):
            continue
        sid = sel.board_snapshot(conn, snaps, t["benchmark"], t["bench_task"])
        board = list(conn.execute("""select model_id, max(score) as score from models.benchmarks where snapshot_id = %s
                                     and benchmark = %s and task = %s group by 1 order by 2 desc""",
                                  (sid, t["benchmark"], t["bench_task"]))) if sid else []
        row = next((r for r in rs if r["task"] == t["task"]), None)
        if not row:
            continue
        rank = next((i + 1 for i, b in enumerate(board) if b["model_id"] == row.get("model_id")), None)
        elo = next((b["score"] for b in board if b["model_id"] == row.get("model_id")), None)
        leader = board[0] if board else None
        out.append({**row, "da_rank": rank, "da_elo": elo, "da_of": len(board),
                    "da_leader": leader["model_id"] if leader else None,
                    "da_leader_elo": leader["score"] if leader else None})
    return out


def render(conn, rs: list[dict], ctx: dict) -> str:
    from .library import _name
    from .alerts import _board_fr
    # --- home: levels + chart --------------------------------------------------------------------------------
    pts = sel.general_points(conn)
    run = conn.execute("select run_id from models.latest_run").fetchone()
    sel_rows = list(conn.execute("""select level, model_id, variant, quality, real_cost from models.selection
                                    where run_id = %s and task = 'general' and level in ('frontier','L1','L2','L3')
                                    order by rank""", (run["run_id"],))) if run else []
    by = {(p["model_id"], p["variant"]): p for p in pts}
    frontier = [by.get((r["model_id"], r["variant"])) or {"model_id": r["model_id"], "variant": r["variant"],
                "name": _name(conn, r["model_id"]), "score": r["quality"], "cost": r["real_cost"]}
                for r in sel_rows if r["level"] == "frontier" and r["real_cost"]]
    levels, level_cards = {}, []
    tiers = {r["category"]: r for r in rs if r["task"] == "general"}
    for lvl in ("L1", "L2", "L3"):
        s = next((r for r in sel_rows if r["level"] == lvl), None)
        card = next((r for r in rs if r["task"] == "general" and r.get("category") == LEVELS[lvl][0]), None) \
            or next((r for r in tiers.values()), None)
        if s:
            p = by.get((s["model_id"], s["variant"])) or {"model_id": s["model_id"], "variant": s["variant"],
                                                           "name": _name(conn, s["model_id"]), "score": s["quality"],
                                                           "cost": s["real_cost"]}
            levels[lvl] = {**p, "short": f'{_name(conn, s["model_id"])} {s["variant"]}'.strip()}
        name, desc = LEVELS[lvl]
        model = (card or {}).get("model") or "—"
        eff = (card or {}).get("model", "")
        effort = next((EFFORT[v] for v in EFFORT if f"({v})" in eff), "")
        score = f'{s["quality"]:.1f}' if s and s["quality"] is not None else "?"
        cost = catalog.money(s["real_cost"]) if s and s["real_cost"] else "?"
        sub = (card or {}).get("subscription")
        fb = (card or {}).get("fallback")
        level_cards.append(
            f'<article class="level lvl-{lvl}"><div class="lvl-head"><span class="lvl-tag">{lvl}</span>'
            f'<span class="lvl-name">{name}</span><span class="lvl-desc">{esc(desc)}</span>'
            + (f'<span class="chip sub">{esc(sub)}</span>' if sub not in (None, "—") else "") + '</div>'
            f'<div class="lvl-main"><div><div class="lvl-model">{esc(model.split(" (")[0])}</div>'
            f'<div class="lvl-effort">réflexion {esc(effort) or "—"}</div></div>'
            f'<div class="kpis"><div><b>{score}</b><span>AA Index</span></div><div><b>{cost} $</b>'
            f'<span>par tâche</span></div></div></div>'
            f'<div class="lvl-route">{_chips((card or {}).get("providers"))}'
            + (f'<span class="lvl-fb">secours : {esc(fb)}</span>' if fb not in (None, "—") else "") + '</div></article>')
    chart = _chart(pts, frontier, levels)
    # --- home: Design Arena specialisations --------------------------------------------------------------------
    da = _da_specialisations(conn, rs)
    da_cards = []
    for r in da:
        rank = f'#{r["da_rank"]}<small>/{r["da_of"]}</small>' if r.get("da_rank") else '<small>non classé</small>'
        lead = "" if not r.get("da_leader") or r["da_leader"] == r.get("model_id") else \
            f'<div class="da-lead">n°1 Design Arena : {esc(_name(conn, r["da_leader"]))} ({r["da_leader_elo"]:.0f})</div>'
        da_cards.append(f'<article class="da"><div class="eyebrow">{esc(r["label"])}</div>'
                        f'<div class="da-row"><div class="model">{esc(r.get("model") or "—")}</div>'
                        f'<div class="da-rank">{rank}</div></div>'
                        f'<div class="da-elo">{"Elo " + format(r["da_elo"], ".0f") if r.get("da_elo") else ""}</div>{lead}'
                        f'<div class="da-prov">{_chips(r.get("providers"))}</div></article>')
    # --- tabs ---------------------------------------------------------------------------------------------------
    panes = {k: [] for k, _, _ in TABS}
    for r in rs:
        if r["task"] == "general":
            continue
        panes[TAB_OF.get(r["type"], "chat")].append(_card(r))
    run_info = ctx.get("run") or {}
    when = run_info.get("finished_at") or run_info.get("started_at")
    when = when.astimezone(timezone.utc).strftime("%d/%m/%Y à %H:%M UTC") if when else "?"
    counts = ctx.get("counts") or {}
    n_diff = sum(1 for r in rs if r.get("differs") and r.get("chosen_by") == "toi")
    down = ctx.get("down") or []
    down_html = "".join(f'<li>{esc(_board_fr(f"{catalog.BOARDS.get(d["subject"].split(":")[0], d["subject"].split(":")[0])} {d["subject"].partition(":")[2]}"))}'
                        f' <span class="muted">— {esc((d["evidence"] or {}).get("reason", ""))}</span></li>' for d in down)
    stats = [("Modèles suivis", ctx.get("tracked", 0)), ("Texte", counts.get("chat", 0)), ("Image", counts.get("image", 0)),
             ("Vidéo", counts.get("video", 0)), ("Audio & musique", counts.get("audio", 0) + counts.get("music", 0)),
             ("Tes choix ≠ n°1", n_diff)]
    nav = "".join(f'<button data-tab="{k}"{" class=on" if k == "home" else ""}>{i} {n}'
                  + (f' <small>{len(panes[k])}</small>' if k != "home" else "") + "</button>" for k, i, n in TABS)
    sections = "".join(f'<section class="pane" data-pane="{k}" hidden><div class="grid">{"".join(v)}</div></section>'
                       for k, v in panes.items() if k != "home")
    generated = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Walter Router · Bibliothèque</title>
<style>
:root{{--bg:#0b0d12;--bg2:#10131a;--card:#151821;--card2:#1a1e29;--line:#252a37;--ink:#eef0f4;--ink2:#b4bac7;
--muted:#7d8496;--accent:#8b7cf6;--accent2:#3987e5;--orange:#d95926;--green:#34d399;--greenbg:rgba(52,211,153,.1);
--amber:#fbbf24;--amberbg:rgba(251,191,36,.09);--red:#f87171;--redbg:rgba(248,113,113,.1);--surface:#12141b}}
*{{box-sizing:border-box}}html{{background:var(--bg)}}
body{{margin:0;color:var(--ink);font:14.5px/1.5 Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
background:radial-gradient(1200px 600px at 10% -10%,rgba(139,124,246,.16),transparent 60%),
radial-gradient(900px 500px at 100% 0%,rgba(57,135,229,.12),transparent 60%),var(--bg);min-height:100vh}}
.wrap{{max-width:1320px;margin:0 auto;padding:0 28px}}
header{{padding:34px 0 18px}}.brand{{display:flex;align-items:center;gap:14px}}
.logo{{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;font-size:22px;
background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 8px 30px rgba(139,124,246,.35)}}
h1{{margin:0;font-size:26px;letter-spacing:-.02em}}.subtitle{{color:var(--muted);margin-top:2px}}
.stats{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-top:22px}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px}}
.stat b{{display:block;font-size:22px;letter-spacing:-.02em}}.stat span{{color:var(--muted);font-size:12px}}
.stat.hl b{{color:var(--amber)}}
nav{{position:sticky;top:0;z-index:5;background:rgba(11,13,18,.82);backdrop-filter:blur(12px);
border-bottom:1px solid var(--line);margin-top:22px}}
.navin{{display:flex;gap:6px;align-items:center;padding:10px 0;overflow-x:auto}}
nav button{{background:none;border:1px solid transparent;color:var(--ink2);padding:8px 14px;border-radius:10px;
font:inherit;cursor:pointer;white-space:nowrap}}nav button:hover{{background:var(--card)}}
nav button.on{{background:var(--card2);border-color:var(--line);color:var(--ink)}}nav small{{color:var(--muted)}}
.tools{{margin-left:auto;display:flex;gap:10px;align-items:center}}
input[type=search]{{background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:10px;
padding:8px 12px;width:260px;font:inherit}}label.f{{color:var(--ink2);font-size:13px;white-space:nowrap}}
main{{padding:26px 0 60px}}h2{{font-size:19px;margin:0 0 4px;letter-spacing:-.01em}}
.lead{{color:var(--muted);margin:0 0 16px}}
.alert{{background:var(--redbg);border:1px solid rgba(248,113,113,.3);color:#fecaca;border-radius:14px;
padding:12px 16px;margin-bottom:22px}}.alert ul{{margin:6px 0 2px;padding-left:20px}}
.home-top{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:20px;align-items:stretch}}
.levels{{display:grid;gap:12px;grid-auto-rows:1fr}}
.level{{position:relative;background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line);
border-radius:18px;padding:16px 18px;overflow:hidden}}
.level:before{{content:"";position:absolute;inset:0 auto 0 0;width:4px}}
.lvl-L1:before{{background:#34d399}}.lvl-L2:before{{background:var(--accent2)}}.lvl-L3:before{{background:var(--accent)}}
.lvl-head{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}.lvl-tag{{font-weight:700;font-size:12px;padding:2px 8px;
border-radius:6px;background:var(--bg2);border:1px solid var(--line)}}.lvl-name{{font-weight:600;font-size:13px}}
.lvl-desc{{color:var(--muted);font-size:12px;flex:1}}.lvl-main{{display:flex;justify-content:space-between;align-items:flex-end;
gap:12px;margin:8px 0 10px}}.lvl-model{{font-size:21px;font-weight:700;letter-spacing:-.02em;line-height:1.2}}
.lvl-effort{{color:var(--accent);font-size:13px}}.kpis{{display:flex;gap:18px;text-align:right}}
.kpis b{{display:block;font-size:19px;letter-spacing:-.01em}}.kpis span{{color:var(--muted);font-size:11.5px}}
.lvl-route{{font-size:12px;display:flex;flex-wrap:wrap;align-items:center;gap:2px}}
.lvl-fb{{color:var(--muted);margin-left:10px}}
.panel{{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px}}
.chart{{position:relative}}.chart svg{{width:100%;height:auto;display:block}}
.gl{{stroke:var(--line);stroke-width:1}}.tick{{fill:var(--muted);font-size:11px}}
.axis{{fill:var(--ink2);font-size:12px}}.pt{{fill:#5b6275;opacity:.55}}.pt:hover{{opacity:1}}
.frontier{{fill:none;stroke:#3987e5;stroke-width:2}}.fpt{{fill:#3987e5;stroke:var(--surface);stroke-width:2}}
.lvl{{fill:#d95926;stroke:var(--surface);stroke-width:2}}.lvl-label{{fill:var(--ink);font-size:12px;font-weight:600}}
.pt,.fpt,.lvl{{cursor:pointer}}
.legend{{display:flex;gap:16px;color:var(--ink2);font-size:12px;margin-top:6px;flex-wrap:wrap}}
.legend i{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px}}
.k-pt{{background:#5b6275}}.k-fr{{background:#3987e5}}.k-lvl{{background:#d95926}}
.tip{{position:absolute;pointer-events:none;background:#0b0d12;border:1px solid var(--line);border-radius:10px;
padding:8px 10px;font-size:12px;display:none;white-space:nowrap;box-shadow:0 8px 24px rgba(0,0,0,.5)}}
.da-wrap{{margin-top:28px}}.da-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}}
.da{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px 16px}}
.da-row{{display:flex;justify-content:space-between;align-items:baseline;gap:8px}}
.da-rank{{font-size:20px;font-weight:700;color:var(--accent)}}.da-rank small{{color:var(--muted);font-size:12px;font-weight:400}}
.da-elo{{color:var(--muted);font-size:12px}}.da-lead{{color:var(--amber);font-size:12px;margin-top:4px}}
.da-prov{{margin-top:8px;font-size:12px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px 18px;transition:.15s}}
.card:hover{{border-color:#353b4d;transform:translateY(-1px)}}.card.differs{{border-color:rgba(251,191,36,.45)}}
.eyebrow{{color:var(--muted);font-size:12px;text-transform:none}}.eyebrow b{{color:var(--ink2);font-weight:600}}
.dot{{margin:0 6px;color:var(--line)}}.title{{display:flex;justify-content:space-between;align-items:baseline;gap:10px}}
.model{{font-size:17px;font-weight:650;letter-spacing:-.01em;margin:4px 0}}
.score{{font-weight:700;color:var(--ink2)}}.score small{{color:var(--muted);font-weight:400}}
.badge{{display:inline-block;font-size:11.5px;padding:2px 9px;border-radius:999px;border:1px solid var(--line)}}
.badge.star{{color:#c4b5fd;background:rgba(139,124,246,.12);border-color:rgba(139,124,246,.35)}}
.badge.calc{{color:#93c5fd;background:rgba(57,135,229,.12);border-color:rgba(57,135,229,.35)}}
.badge.tier{{color:#6ee7b7;background:rgba(52,211,153,.1);border-color:rgba(52,211,153,.3)}}
.note{{margin-top:10px;padding:7px 10px;border-radius:10px;font-size:12.5px}}
.note.amber{{background:var(--amberbg);color:var(--amber)}}.note.warn{{background:var(--redbg);color:var(--red)}}
dl{{display:grid;grid-template-columns:86px 1fr;gap:6px 10px;margin:12px 0 0;font-size:12.5px}}
dt{{color:var(--muted)}}dd{{margin:0}}.chip{{display:inline-block;background:var(--bg2);border:1px solid var(--line);
border-radius:7px;padding:1px 7px;margin:1px 0;color:var(--ink2)}}.chip.sub{{color:var(--green);background:var(--greenbg);
border-color:rgba(52,211,153,.25)}}.sep{{color:var(--muted);margin:0 4px}}.muted{{color:var(--muted)}}
.card.empty .model{{color:var(--red)}}[hidden]{{display:none!important}}.hide{{display:none!important}}
footer{{color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding:18px 0 40px}}
@media (max-width:980px){{.home-top{{grid-template-columns:1fr}}.stats{{grid-template-columns:repeat(3,1fr)}}
.tools input{{width:160px}}}}
@media (max-width:560px){{.wrap{{padding:0 14px}}.stats{{grid-template-columns:repeat(2,1fr)}}.tools{{display:none}}}}
</style></head><body>
<div class="wrap"><header><div class="brand"><div class="logo">🧭</div><div><h1>Walter Router · Bibliothèque</h1>
<div class="subtitle">Dernier cycle le {esc(when)} · mise à jour automatique toutes les 48 h et après chacune de tes réponses</div></div></div>
<div class="stats">{"".join(f'<div class="stat{" hl" if lbl.startswith("Tes") else ""}"><b>{v}</b><span>{esc(lbl)}</span></div>' for lbl, v in stats)}</div>
</header></div>
<nav><div class="wrap navin">{nav}<div class="tools"><input type="search" id="q" placeholder="Rechercher un modèle, un fournisseur…">
<label class="f"><input type="checkbox" id="diff"> mes choix ≠ n°1</label></div></div></nav>
<main class="wrap">
{f'<div class="alert"><b>⚠️ Classements inaccessibles</b><ul>{down_html}</ul>Le router garde leur dernière lecture valable pendant 21 jours.</div>' if down else ''}
<section class="pane" data-pane="home">
<div class="home-top"><div><h2>🧠 Niveaux de réflexion</h2><p class="lead">Optimum de Pareto calculé par ta méthode (coudes de la frontière AA)</p>
<div class="levels">{"".join(level_cards)}</div></div>
<div class="panel"><h2>AA Intelligence Index × coût réel</h2><p class="lead">{len(pts)} modèles × niveau de réflexion exécutables · survole un point</p>{chart}</div></div>
<div class="da-wrap"><h2>🎨 Spécialisations Design Arena</h2><p class="lead">Rang du modèle retenu sur le classement Design Arena de chaque tâche</p>
<div class="da-grid">{"".join(da_cards)}</div></div>
</section>
{sections}
</main>
<div class="wrap"><footer>⭐ Ton choix = modèle que tu as fixé · « ≠ n°1 » = le mieux classé est un autre (raison indiquée) ·
🤖 Calculé = meilleur modèle exécutable selon les classements pondérés · 📐 Méthode Pareto = niveaux L1/L2/L3.
Prix : texte en $ par million de tokens (entrée/sortie), image par image, vidéo par seconde (plage selon la résolution),
« ≈ estimé » quand le fournisseur facture au token. Page générée le {generated}.</footer></div>
<script>
const tabs=document.querySelectorAll('nav button'),panes=document.querySelectorAll('.pane'),q=document.getElementById('q'),
d=document.getElementById('diff');let cur='home';
function show(t){{cur=t;tabs.forEach(b=>b.classList.toggle('on',b.dataset.tab===t));
panes.forEach(p=>p.hidden=p.dataset.pane!==t);filter()}}
function filter(){{const s=(q.value||'').trim().toLowerCase();if((s||d.checked)&&cur==='home'){{show('chat');return}}
document.querySelectorAll('.card').forEach(c=>c.classList.toggle('hide',!((!s||c.dataset.search.includes(s))&&(!d.checked||c.dataset.differs==='1'))))}}
tabs.forEach(b=>b.onclick=()=>show(b.dataset.tab));q.oninput=filter;d.onchange=()=>{{if(d.checked&&cur==='home')show('video');filter()}};
const tip=document.getElementById('tip');document.querySelectorAll('[data-tip]').forEach(el=>{{
el.addEventListener('mouseenter',e=>{{const o=JSON.parse(el.dataset.tip);tip.innerHTML='<b>'+o.n+'</b><br>Index '+o.s+' · '+o.c+' $ / tâche'+(o.p?' · '+o.p:'');tip.style.display='block'}});
el.addEventListener('mousemove',e=>{{const r=tip.parentElement.getBoundingClientRect();tip.style.left=(e.clientX-r.left+14)+'px';tip.style.top=(e.clientY-r.top-10)+'px'}});
el.addEventListener('mouseleave',()=>tip.style.display='none')}});
show('home');
</script></body></html>"""

"""Library web page (v3, 2026-10-14: « le design fait trop IA, pas pro »).

Editorial / market-terminal posture: paper background, black ink, one accent, hairline rules, dense tables with
tabular figures, no emoji, no gradient, no pill badges. Home: the three reasoning levels (Pareto optimum of
the owner's method) beside the AA chart, then the Design Arena specialisations. Tabs: Texte, Image, Vidéo,
Audio & musique, Décision. Self-contained HTML; chart in inline SVG with hover. Chart palette validated with the
dataviz validator: light #2a78d6 / #eb6834 on #ffffff, dark #3987e5 / #d95926 on #141414.
"""
from __future__ import annotations

import html
import json
import math
from datetime import datetime, timezone

from walter_router.analysis import catalog
from walter_router.analysis import select as sel

esc = html.escape
TABS = [("home", "🏠", "Vue d'ensemble"), ("chat", "💬", "Texte"), ("image", "🖼️", "Image"), ("video", "🎬", "Vidéo"),
        ("audio", "🎧", "Audio & musique"), ("memory", "🔎", "Mémoire & recherche"), ("decisions", "🧭", "Décision"),
        ("subs", "💳", "Abonnements")]
TAB_OF = {"chat": "chat", "image": "image", "video": "video", "audio": "audio", "music": "audio", "decisions": "decisions",
          "transcription": "audio", "embedding": "memory", "rerank": "memory"}   # services (2026-10-17)
LEVELS = {"L1": ("Économique", "Quotidien : réponses courtes, résumés, petites rédactions"),
          "L2": ("Intermédiaire", "Analyse en plusieurs étapes, comparaison, rédaction soignée"),
          "L3": ("Haut de gamme", "Raisonnement profond, synthèse, enjeu important")}
EFFORT = {"low": "faible", "medium": "moyenne", "high": "élevée", "xhigh": "très élevée", "max": "maximale"}
ORIGIN = {"toi": "Ton choix", "calcul": "Calculé", "méthode des niveaux": "Méthode Pareto"}


def _route(text: str | None) -> str:
    if not text or text == "—":
        return '<span class="mute">—</span>'
    return '<span class="arr"> → </span>'.join(f'<span class="nw">{esc(p.strip())}</span>' for p in text.split("→"))


def _chart(points: list[dict], frontier: list[dict], levels: dict[str, dict], key: str = "cost") -> str:
    points = [{**p, "cost": p[key]} for p in points if p.get(key)]
    frontier = [{**p, "cost": p[key]} for p in frontier if p.get(key)]
    levels = {k: {**p, "cost": p[key]} for k, p in levels.items() if p.get(key)}
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
    axis = "coût réel par tâche AA (meilleur fournisseur)" if key == "cost" else "coût officiel par tâche AA (prix de référence)"
    return (f'<figure class="chart" data-cost="{key}"{" hidden" if key != "cost" else ""}><svg viewBox="0 0 {W} {H}" role="img" aria-label="Indice AA en fonction du coût '
            f'réel par tâche">{"".join(g)}</svg><figcaption><span><i class="k1"></i>Modèles exécutables</span>'
            f'<span><i class="k2"></i>Frontière de Pareto</span><span><i class="k3"></i>Niveaux retenus</span>'
            f'<span class="mute">Abscisse : {axis}, échelle logarithmique</span></figcaption>'
            f'<div class="tip"></div></figure>')


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
    head = ('<thead><tr><th>Tâche</th><th>Modèle</th><th>Origine</th><th class="num" title="Score /100 : moyenne pondérée des classements indiqués sous chaque tâche">Score</th>'
            '<th>Fournisseurs (ordre, prix)</th><th>Secours</th><th>Abonnement</th></tr></thead>')
    body, last = [], None
    multi = {r["label"] for r in rs if r.get("category")}   # tasks split into categories get a group header row
    for r in rs:
        differs = bool(r.get("differs")) and r.get("chosen_by") == "toi"
        first = r["label"] != last
        last = r["label"]
        bench = (f'<div class="bench" data-en="Leaderboards: {esc(r.get("boards_en") or "")}">'
                 f'Classements : {esc(r["boards"])}</div>') if r.get("boards") else ""
        if first and r["label"] in multi:
            body.append(f'<tr class="grp"><td colspan="7"><span class="gname">{esc(r["label"])}</span>{bench}</td></tr>')
            task = ""
        else:
            task = (esc(r["label"]) + bench) if first else ""
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
            f'<td class="nw">{esc(r["subscription"]) if r.get("subscription") not in (None, "—") else ""}</td></tr>')
    return f'<div class="tw"><table class="lib">{head}<tbody>{"".join(body)}</tbody></table></div>'


def _tok(n: float | None) -> str:
    if not n:
        return "—"
    return f"{n / 1e9:.2f} Md".replace(".", ",") if n >= 1e9 else f"{n / 1e6:.0f} M"


def _usd(x: float | None) -> str:
    return "—" if x is None else (f"{x:,.0f} $".replace(",", " ") if x >= 100 else f"{catalog.money(x)} $")


def _subscriptions(conn) -> tuple[str, int]:
    """Subscriptions pane (information only): our measurement on the owner's account + SemiAnalysis' plan values."""
    from walter_router.plan import subscriptions
    from walter_router.interface.library import _name
    try:
        subs = subscriptions.state(conn)
        semi = subscriptions.doc()["semianalysis"]
    except Exception as exc:  # noqa: BLE001 — the page must still publish
        return f'<p class="notice">Abonnements indisponibles : {esc(type(exc).__name__)}</p>', 0
    usage_rows, cap_rows = [], []
    for s in subs:
        m, u = s["meter"], s["usage_7d"]
        if not m:
            meter, reset = '<span class="mute">non lu</span>', "—"
        elif m["estimated"]:
            meter = (f'≈ {m["used_percent"]:.0f} %<div class="mute small">estimé'
                     + ("" if m["calibrated"] else ", à calibrer") + "</div>")
            reset = '<span class="mute">7 jours glissants</span>'
        else:
            meter = f'{m["used_percent"]:.0f} %<div class="mute small">réel</div>'
            reset = m["resets_at"].astimezone(timezone.utc).strftime("%d/%m/%Y, %H:%M UTC") if m["resets_at"] else "—"
        cached = u["tokens"]["cache_read"] / u["total_tokens"] * 100 if u["total_tokens"] else None
        usage_rows.append(
            f'<tr><td class="model">{esc(s["name"])}<div class="mute small">{esc(s["vendor"])}</div></td>'
            f'<td class="num">{s["price_usd_month"]} $<div class="mute small">par mois</div></td>'
            f'<td>{esc(s["execution"])}</td><td class="num">{meter}</td><td class="nw">{reset}</td>'
            f'<td class="num">{_tok(u["total_tokens"])}</td>'
            f'<td class="num">{"—" if cached is None else f"{cached:.0f} %"}</td>'
            f'<td class="num">{_usd(u["api_value_usd"])}</td>'
            f'<td class="num strong">{_usd(s["usd_per_m_at_pace"])}</td></tr>')
        first = True

        def row(model: str, source: str, value, multiple, tokens, per_m, note: str = "") -> None:
            nonlocal first
            mult = "—" if multiple is None else f"{multiple:g} ×".replace(".", ",")
            cap_rows.append(
                f'<tr><td class="model nw">{esc(s["name"]) if first else ""}</td><td class="nw">{model}</td><td>{source}{note}</td>'
                f'<td class="num">{_usd(value)}</td><td class="num">{mult}</td>'
                f'<td class="num">{_tok(tokens)}</td><td class="num strong">{_usd(per_m)}</td></tr>')
            first = False
        mine = s["measured_capacity"]
        if mine:
            row("Forfait entier", "Notre mesure", mine["month_usd"], mine["multiple"], None, None,
                f'<div class="mute small">{mine["points"]:.0f} points de compteur</div>')
        elif s["id"] == "openai-plus":
            row("Forfait entier", "Notre mesure", None, None, None, None,
                '<div class="mute small">en cours : il faut 3 points de compteur dans une même semaine</div>')
        else:
            row("Forfait entier", "Notre mesure", None, None, None, None,
                '<div class="mute small">à calibrer avec le pourcentage hebdomadaire affiché par claude.ai</div>')
        for v in s["semianalysis"]:
            row(esc(_name(conn, v["model_id"])), "SemiAnalysis", v["usd_month"], v["multiple"], v["tokens_month"],
                v["usd_per_m_full"])
        for model, why in s["excluded"].items():
            row(esc(_name(conn, model)), '<span class="mute">—</span>', None, None, None, None,
                f'<div class="mute small">{esc(EXCLUDED.get(why, why))}</div>')
    share = f'{semi["workload_mix"]["cache_read"] * 100:.1f}'.replace(".", ",")
    date = semi["date"]
    return (
        '<h2>💳 Abonnements</h2><p class="dek">Ce que tes forfaits valent au prix API, le prix de revient d’un token par '
        'forfait (il entre dans le choix du fournisseur), ce que l’on sait de chaque plan, et la modification de tes plans.</p>'
        + _plan_costs(conn) + _plan_facts(conn) + _plan_forms(subs) +
        '<h3>Compteur et consommation des 7 derniers jours</h3>'
        '<div class="tw"><table><thead><tr><th>Abonnement</th><th class="num">Prix</th><th>Utilisé par</th>'
        '<th class="num">Compteur hebdo</th><th>Remise à zéro</th><th class="num">Tokens</th>'
        '<th class="num">Lus en cache</th><th class="num">Valeur API</th><th class="num">Coût du million à ton rythme</th>'
        f'</tr></thead><tbody>{"".join(usage_rows)}</tbody></table></div>'
        '<h3 class="block">Capacité du forfait utilisé à 100 %</h3>'
        '<div class="tw"><table><thead><tr><th>Abonnement</th><th>Modèle</th><th>Source</th>'
        '<th class="num">Valeur API par mois</th><th class="num">× le prix</th><th class="num">Tokens par mois</th>'
        f'<th class="num">Coût du million</th></tr></thead><tbody>{"".join(cap_rows)}</tbody></table></div>'
        '<p class="mute small note">Valeur API = tokens réellement consommés, au prix catalogue de l’éditeur. '
        'Tokens vus sur la VM : Hermes et Codex pour ChatGPT Plus, Claude Code pour Claude Pro. '
        'Coût du million à ton rythme = prix de la semaine ÷ tokens de la semaine. '
        'Notre mesure ChatGPT = valeur API consommée entre deux lectures du compteur ÷ points gagnés, ramenée à 100 % '
        '(un plancher : l’usage hors de la VM fait monter le compteur sans tokens vus ici). '
        'Compteur Claude estimé = entrée + écriture en cache + 5 × sortie, lectures en cache gratuites, sur une capacité '
        'tirée de SemiAnalysis tant qu’il n’est pas calibré. '
        f'SemiAnalysis, rapport du {date} : valeur du forfait entièrement utilisé, sur un usage agentique de {share} % '
        'de lectures en cache ; tokens par mois = valeur ÷ prix moyen du million sur ce mélange.</p>'), len(subs)


ORIGIN_ICON = {"web": "🌐 web", "email": "📧 mail", "owner": "✍️ toi", "measure": "📏 mesure"}
METRIC_FR = {"usd_value_month": "valeur API par mois", "tokens_month": "tokens par mois", "messages_5h": "messages par 5 h",
             "messages_week": "messages par semaine", "price_usd_month": "prix par mois", "limit_note": "limite",
             "plan_change": "événement"}


def _plan_costs(conn) -> str:
    """Cost price of a token per plan (2026-10-22): what the router uses to price a subscription route."""
    rows = []
    for r in conn.execute("""select c.*, extract(epoch from now() - c.at) / 3600 as age_h from models.latest_subscription_costs c
                             order by sub_id"""):
        pct = lambda x: "—" if x is None else f"{x * 100:.1f}".replace(".", ",") + "\u202f%"
        quota = "—" if r["used_percent"] is None else f'{r["used_percent"]:.0f}\u202f%'
        rows.append(f'<tr><td class="model">{esc(r["sub_id"])}</td><td class="num strong">{pct(r["ratio_pace"])}</td>'
                    f'<td class="num">{pct(r["ratio_full"])}</td><td class="num">{_usd(r["api_value_month_pace"])}</td>'
                    f'<td class="num">{_usd(r["api_value_month_full"])}</td><td class="num">{quota}</td>'
                    f'<td class="num mute small">{r["age_h"]:.0f} h</td></tr>')
    if not rows:
        return ""
    return ('<h3>Prix de revient d’un token</h3><div class="tw"><table><thead><tr><th>Abonnement</th>'
            '<th class="num">À ton rythme</th><th class="num">Forfait utilisé à 100 %</th><th class="num">Valeur API par mois (rythme)</th>'
            '<th class="num">Valeur API par mois (capacité)</th><th class="num">Quota hebdo</th><th class="num">Âge de la mesure</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div><p class="mute small note">Prix de revient = prix du forfait ÷ valeur '
            'API qu’il transporte par mois, en part du prix API. Un chemin par abonnement passe en premier tant que son quota '
            'hebdomadaire reste sous 90 %, puis après les fournisseurs payants.</p>')


def _plan_facts(conn) -> str:
    """Everything known about each plan, with its source (web research, billing mails, measures, the owner)."""
    rows = []
    for r in conn.execute("""select * from models.plan_evidence
                             where plan <> 'crédit'   -- pay-as-you-go top-ups (OpenRouter, API credits) are not plans
                             order by plan, origin = 'email', published desc nulls last, found_at desc limit 60"""):
        val = "" if r["value"] is None else (f'{r["value"]:g} '.replace(".", ","))
        src = (f'<a href="{esc(r["source_url"])}" rel="noopener" target="_blank"><span class="raw">{esc(r["source_name"])}</span></a>'
               if (r["source_url"] or "").startswith("http") else f'<span class="raw">{esc(r["source_name"])}</span>')
        rows.append(f'<tr><td class="model nw"><span class="raw">{esc(r["plan"])}</span></td><td>{METRIC_FR.get(r["metric"], r["metric"])}</td>'
                    f'<td><span class="raw">{esc(val + (r["unit"] or ""))}</span><div class="mute small"><span class="raw">{esc((r["quote"] or "")[:140])}</span></div></td>'
                    f'<td>{src}</td><td class="nw">{r["published"] or "—"}</td><td class="nw">{ORIGIN_ICON.get(r["origin"], r["origin"])}</td></tr>')
    if not rows:
        return ""
    return ('<h3 class="block">Ce que l’on sait de chaque plan</h3><div class="tw"><table><thead><tr><th>Plan</th><th>Quoi</th>'
            '<th>Valeur</th><th>Source</th><th>Date</th><th>Trouvé par</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _plan_forms(subs: list[dict]) -> str:
    """Edit a plan, cancel it, or add one (2026-10-22). Sent to /api/plans (Access + HMAC), applied by
    `walter-router plans`; the page is republished after the change."""
    def form(pid: str, s: dict) -> str:
        new = not pid
        return (f'<form class="planform" data-id="{esc(pid)}"><div class="pf-title">{"Nouvel abonnement" if new else esc(s.get("name") or pid)}</div>'
                + ('<label>Identifiant<input name="sub_id" placeholder="ex. google-ai-pro" required></label>' if new else "")
                + f'<label>Éditeur<input name="vendor" value="{esc(s.get("vendor") or "")}"></label>'
                f'<label>Plan<input name="plan" value="{esc(s.get("plan_name") or "")}"></label>'
                f'<label>Prix par mois ($)<input name="price_usd_month" type="number" step="0.01" min="0" value="{s.get("price_usd_month") or ""}"></label>'
                f'<label>Modèles inclus<input name="models" value="{esc(", ".join(s.get("models") or []))}" placeholder="ids séparés par des virgules"></label>'
                f'<label>Note<input name="note" value="{esc(s.get("note") or "")}"></label>'
                '<div class="pf-actions"><button type="submit">Enregistrer</button>'
                + ("" if new else '<button type="button" class="pf-retire">Résilier</button>') +
                '<span class="pf-state mute small"></span></div></form>')
    from walter_router.plan import declared
    raw = {d["id"]: d for d in declared.read().get("subscriptions", [])}
    forms = [form(s["id"], {**raw.get(s["id"], {}), "name": s["name"], "plan_name": raw.get(s["id"], {}).get("plan")}) for s in subs]
    forms.append(form("", {}))
    return ('<h3 class="block">Modifier mes abonnements</h3><p class="mute small">Aussi possible dans la discussion '
            '(« walter-router plans set … ») ; un mail de facturation qui ne correspond pas devient une proposition sur Telegram.</p>'
            f'<div class="planforms">{"".join(forms)}</div>')



EXCLUDED = {"not included in Pro (usage credits at API price)": "non inclus dans Pro (crédits payés au prix API)"}


def render(conn, rs: list[dict], ctx: dict) -> str:
    from walter_router.interface.library import _name
    from walter_router.analysis.telegram import _board_fr
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
        aa = (by.get((s["model_id"], s["variant"])) or {}).get("cost_aa")
        cost_aa = f'{catalog.money(aa)} $' if aa else "—"
        lrows.append(
            f'<tr><td class="lvl">{lvl}</td><td><div class="lname">{LEVELS[lvl][0]}</div></td>'
            f'<td class="model">{esc((card.get("model") or "—").split(" (")[0])}<div class="mute small">réflexion {effort}</div></td>'
            f'<td class="num" data-label="Indice AA">{f"{s["quality"]:.1f}".replace(".", ",")}</td><td class="num" data-label="Coût AA officiel">{cost_aa}</td><td class="num strong" data-label="Coût réel">{cost}</td></tr>'
            f'<tr class="sub"><td></td><td colspan="5"><div class="mute desc">{LEVELS[lvl][1]}</div><span class="mute">Fournisseurs</span> {_route(card.get("providers"))}'
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
    panes = {k: [r for r in rs if r["task"] != "general" and TAB_OF.get(r["type"]) == k] for k, _, _ in TABS}
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
    subs_html, n_subs = _subscriptions(conn)
    nav = "".join(f'<a href="#{k}" data-tab="{k}"{" class=on" if k == "home" else ""}><span class="ic">{i}</span>{n}'
                  + (f'<span class="ct">{n_subs if k == "subs" else len(panes[k])}</span>' if k != "home" else "")
                  + "</a>" for k, i, n in TABS)
    tab_html = "".join(f'<section class="pane" data-pane="{k}" hidden><h2>{i} {n}</h2>{_table(panes[k])}</section>'
                       for k, i, n in TABS if k not in ("home", "subs"))
    tab_html += f'<section class="pane" data-pane="subs" hidden>{subs_html}</section>'
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
header{{padding:32px 0 22px}}.foot-figs{{color:var(--ink2);margin-bottom:8px}}.kicker{{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute)}}
h1{{font:600 30px/1.15 Georgia,"Times New Roman",serif;letter-spacing:-.01em;margin:6px 0 4px}}
.meta{{color:var(--mute);font-size:13px}}
.figures{{display:grid;grid-template-columns:repeat(6,1fr);border-top:2px solid var(--ink);border-bottom:1px solid var(--rule);
margin-top:22px}}.figures div{{padding:12px 14px 12px 0}}.figures div+div{{border-left:1px solid var(--rule);padding-left:14px}}
.figures b{{display:block;font-size:22px;font-weight:600;letter-spacing:-.01em}}.figures span{{color:var(--mute);font-size:12px}}
.figures .hl b{{color:var(--amber)}}
nav{{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--rule2);padding:12px 0}}
.navin{{display:flex;align-items:center;gap:20px;flex-wrap:wrap}}.seg[role=tablist]{{max-width:100%;overflow-x:auto;scrollbar-width:none}}
.seg{{display:inline-flex;border:1px solid var(--rule2);border-radius:8px;padding:3px;background:var(--paper);gap:2px}}
.seg a,.seg button{{display:inline-flex;align-items:center;gap:7px;color:var(--ink2);text-decoration:none;padding:7px 13px;
border-radius:6px;white-space:nowrap;font:500 13.5px/1 inherit;font-family:inherit;border:0;background:none;cursor:pointer}}
.seg a:hover,.seg button:hover{{background:var(--bg);color:var(--ink)}}
.seg a.on,.seg button.on{{background:var(--ink);color:var(--paper)}}.seg .ic{{font-size:14px}}
.seg .ct{{font-size:11px;padding:2px 6px;border-radius:999px;background:var(--bg);color:var(--mute);border:1px solid var(--rule)}}
.seg a.on .ct{{background:transparent;color:var(--paper);border-color:rgba(255,255,255,.35)}}
.small-seg{{margin:0 0 10px}}.small-seg button{{padding:5px 11px;font-size:12.5px}}
.headrow{{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap}}.desc{{margin-bottom:3px}}
.run{{text-align:right;padding-top:4px}}#runbtn{{font:600 13px/1 inherit;font-family:inherit;padding:10px 16px;border-radius:7px;border:1px solid var(--ink);
background:var(--ink);color:var(--paper);cursor:pointer}}#runbtn:hover{{opacity:.88}}#runbtn:disabled{{opacity:.5;cursor:default}}
#runstate{{margin-top:6px;min-height:16px}}.strong{{font-weight:600}}
.tools{{margin-left:auto;display:flex;gap:16px;align-items:center}}
input[type=search]{{border:0;border-bottom:1px solid var(--rule2);background:transparent;color:var(--ink);padding:6px 2px;
width:170px;font:inherit;outline:none}}input[type=search]:focus{{border-bottom-color:var(--ink)}}
label.f{{font-size:13px;color:var(--ink2);white-space:nowrap}}
main.wrap{{padding-top:30px;padding-bottom:64px}}
h2{{font:600 19px/1.3 Georgia,"Times New Roman",serif;margin:0 0 2px}}.dek{{color:var(--mute);margin:0 0 14px;font-size:13px}}
.notice{{color:var(--red);font-size:13px;margin:0 0 22px;padding:8px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}}
.split{{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,6fr);gap:40px}}
table{{width:100%;border-collapse:collapse}}th{{text-align:left;font-weight:600;font-size:11px;letter-spacing:.06em;
text-transform:uppercase;color:var(--mute);padding:8px 10px 8px 0;border-bottom:1px solid var(--ink)}}
td{{padding:10px 10px 10px 0;border-bottom:1px solid var(--rule);vertical-align:top}}
.num{{text-align:right;white-space:nowrap}}th.num{{text-align:right}}
.levels td{{border-bottom:0;padding-bottom:2px}}.levels tr.sub td{{border-bottom:1px solid var(--rule);padding-top:0;padding-bottom:12px;
font-size:12.5px;color:var(--ink2)}}.lvl{{font-weight:700;font-size:15px;width:34px}}.lname{{font-weight:600;white-space:nowrap}}
.planforms{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:18px;margin:8px 0 28px}}.planform{{border:1px solid var(--rule);padding:14px 16px;display:flex;flex-direction:column;gap:8px}}.planform .pf-title{{font-weight:600;margin-bottom:2px}}.planform label{{display:flex;flex-direction:column;font-size:12px;color:var(--mute);gap:3px}}.planform input{{font:inherit;font-size:14px;color:inherit;padding:6px 8px;border:1px solid var(--rule);background:transparent}}.pf-actions{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:4px}}.pf-actions button{{font:inherit;font-size:13px;padding:6px 12px;border:1px solid currentColor;background:transparent;cursor:pointer}}.pf-actions button[type=submit]{{background:var(--ink,#111);color:var(--bg,#fff);border-color:var(--ink,#111)}}
.model{{font-weight:600}}.levels .model{{white-space:nowrap}}.small{{font-size:12px;font-weight:400}}.mute{{color:var(--mute)}}.sep2{{margin-left:14px}}
.arr{{color:var(--mute)}}.nw{{white-space:nowrap}}.amber{{color:var(--amber);font-size:12.5px}}
.lib td.task{{width:21%;font-weight:600}}.lib .cat{{font-weight:400;color:var(--ink2)}}.lib td.route{{font-size:12.5px}}
.lib td{{font-size:13px}}.origin{{color:var(--mute);white-space:nowrap}}.origin.mine{{color:var(--ink);font-weight:600}}
.bench{{font-weight:400;font-size:11.5px;color:var(--mute);margin-top:3px;line-height:1.4}}
tr.grp td{{padding:16px 0 6px;border-bottom:1px solid var(--rule2)}}tr.grp .gname{{font-weight:700;font-size:13.5px}}
tr.grp .bench{{display:inline;margin-left:12px}}.lib td.task .cat{{font-weight:600;color:var(--ink)}}
.n-amber{{font-weight:400;font-size:12px;color:var(--amber);margin-top:3px}}.n-red{{font-weight:400;font-size:12px;color:var(--red);margin-top:3px}}
tr.diff td{{background:var(--amberbg)}}.tw{{overflow-x:auto;-webkit-overflow-scrolling:touch}}.tw table.lib{{min-width:980px}}.tw table{{min-width:720px}}.tw table.levels{{min-width:0}}
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
.block{{margin-top:44px}}h3{{font:600 15px/1.3 Georgia,"Times New Roman",serif;margin:18px 0 8px}}h3.block{{margin-top:36px}}
.note{{max-width:900px;margin-top:18px;line-height:1.6}}[hidden]{{display:none!important}}.hide{{display:none!important}}
footer{{border-top:1px solid var(--rule2);color:var(--mute);font-size:12px;padding:16px 0 40px;line-height:1.6}}
.lang{{margin-top:14px;font-size:13px}}.lang a{{color:var(--ink2);text-decoration:none;padding:2px 0}}.lang a:hover{{color:var(--ink)}}
.lang a.on{{color:var(--ink);font-weight:600;border-bottom:1px solid var(--ink)}}.lang .sep{{margin:0 8px;color:var(--mute)}}
@media (max-width:980px){{.split{{grid-template-columns:1fr}}.figures{{grid-template-columns:repeat(3,1fr)}}
.figures div:nth-child(4){{border-left:0;padding-left:0}}}}
@media (max-width:1100px){{.tools{{margin-left:0;width:100%;justify-content:space-between}}input[type=search]{{flex:1}}}}
@media (max-width:600px){{.levels thead{{display:none}}.levels tr:not(.sub){{display:flex;flex-wrap:wrap;align-items:baseline}}
.levels tr:not(.sub) td{{border:0;padding:12px 0 0}}.levels td.lvl{{width:34px}}.levels tr:not(.sub) td:nth-child(2){{flex:1}}
.levels colgroup{{display:none}}.levels td{{width:auto!important}}.levels td.lvl{{flex:0 0 34px}}.levels{{table-layout:auto}}
.levels td.model{{flex:0 0 100%;padding:4px 0 0 34px!important;white-space:normal}}
.levels td.num{{flex:1 1 0;min-width:0;text-align:left;padding:10px 0 0 34px!important}}.levels td.num+td.num{{padding-left:12px!important}}
.levels td.num::before{{content:attr(data-label);display:block;color:var(--mute);font-size:11px;font-weight:400;letter-spacing:.04em;text-transform:uppercase}}
.levels tr.sub td{{padding-left:34px}}.levels tr.sub td:first-child{{display:none}}}}
@media (max-width:600px){{.wrap{{padding:0 16px}}.figures{{grid-template-columns:repeat(2,1fr)}}
.figures div{{border-left:0!important;padding-left:0!important}}}}
</style></head><body>
<div class="wrap"><header><div class="headrow"><div><div class="kicker">Walter Router</div><h1>Bibliothèque des modèles</h1></div>
<div class="run"><button id="runbtn" type="button">▶ Lancer le cycle complet</button><div id="runstate" class="mute small"></div></div></div>
</header></div>
<nav><div class="wrap navin"><div class="seg" role="tablist">{nav}</div><div class="tools"><input type="search" id="q" placeholder="Rechercher">
<label class="f"><input type="checkbox" id="diff"> Mes choix ≠ n°1 <span class="mute">({n_diff})</span></label></div></div></nav>
<main class="wrap">
{f'<p class="notice">Classement inaccessible : {esc(down_txt)}. Le router conserve sa dernière lecture valable pendant 21 jours.</p>' if down else ''}
<section class="pane" data-pane="home">
<div class="split"><div><h2>🧠 Niveaux de réflexion</h2><p class="dek">Optimum de Pareto calculé par ta méthode sur la frontière AA</p>
<div class="tw"><table class="levels"><colgroup><col style="width:34px"><col style="width:120px"><col><col style="width:64px"><col style="width:84px"><col style="width:84px"></colgroup><thead><tr><th></th><th>Niveau</th><th>Modèle</th><th class="num">Indice AA</th><th class="num" title="Prix de référence publié par Artificial Analysis">Coût AA officiel</th><th class="num" title="Recalculé avec le prix du fournisseur utilisé">Coût réel</th></tr></thead>
<tbody>{"".join(lrows)}</tbody></table></div></div>
<div><h2>📈 Indice d'intelligence et coût par tâche</h2><p class="dek">{len(pts)} combinaisons modèle × niveau de réflexion exécutables</p><div class="seg small-seg" id="costseg"><button data-cost="cost" class="on">Coût réel</button><button data-cost="cost_aa">Coût AA officiel</button></div>
{_chart(pts, frontier, levels)}{_chart(pts, frontier, levels, "cost_aa")}</div></div>
<div class="block"><h2>🎨 Spécialisations Design Arena</h2><p class="dek">Rang du modèle retenu sur le classement Design Arena de chaque tâche</p>
<div class="tw"><table><thead><tr><th>Tâche</th><th>Modèle retenu</th><th class="num">Rang</th><th class="num">Score</th>
<th>N°1 Design Arena, si différent</th><th>Fournisseurs</th></tr></thead><tbody>{"".join(da_rows)}</tbody></table></div></div>
</section>
{tab_html}
</main>
<div class="wrap"><footer><div class="foot-figs">{" · ".join(f"{esc(lbl)} {v}" for lbl, v in figures if not lbl.startswith("Tes"))}.
Classements recalculés le {esc(when)} ; cycle complet automatique toutes les 48 heures, page republiée après chacune de tes réponses.</div>Origine : « Ton choix » = modèle fixé par toi ; « Calculé » = meilleur modèle exécutable selon les classements
pondérés ; « Méthode Pareto » = niveaux L1, L2, L3. Une ligne surlignée signale un choix de ta part différent du n°1 mesuré, avec la raison.
Prix : texte en dollars par million de tokens (entrée/sortie), image par image, vidéo par seconde (plage selon la résolution) ;
« estimé » lorsque le fournisseur facture au token. Page générée le {generated}.
<div class="lang"><a href="/" data-lang="en">English</a><span class="sep">·</span><a href="/fr/" data-lang="fr" class="on">Français</a></div></footer></div>
<script>
(function(){{const want=localStorage.getItem('walterLang'),here=document.documentElement.lang;
if(want&&want!==here){{location.replace((want==='fr'?'/fr/':'/')+location.hash);return}}
document.querySelectorAll('.lang a').forEach(a=>a.addEventListener('click',()=>localStorage.setItem('walterLang',a.dataset.lang)))}})();
const links=document.querySelectorAll('nav a[data-tab]'),panes=document.querySelectorAll('.pane'),q=document.getElementById('q'),
d=document.getElementById('diff');let cur='home';
function show(t){{cur=t;links.forEach(a=>{{a.classList.toggle('on',a.dataset.tab===t);if(a.dataset.tab===t)a.scrollIntoView({{block:'nearest',inline:'nearest'}})}});panes.forEach(p=>p.hidden=p.dataset.pane!==t);filter()}}
function filter(){{const s=(q.value||'').trim().toLowerCase();if((s||d.checked)&&cur==='home'){{show(d.checked?'video':'chat');return}}
document.querySelectorAll('tbody tr[data-search]').forEach(r=>r.classList.toggle('hide',!((!s||(r.dataset.search+' '+r.textContent.toLowerCase()).includes(s))&&(!d.checked||r.dataset.differs==='1'))))}}
links.forEach(a=>a.onclick=e=>{{e.preventDefault();show(a.dataset.tab);history.replaceState(null,'','#'+a.dataset.tab)}});
q.oninput=filter;d.onchange=filter;
document.querySelectorAll('#costseg button').forEach(b=>b.onclick=()=>{{
document.querySelectorAll('#costseg button').forEach(x=>x.classList.toggle('on',x===b));
document.querySelectorAll('figure.chart').forEach(f=>f.hidden=f.dataset.cost!==b.dataset.cost)}});
document.querySelectorAll('[data-tip]').forEach(el=>{{const tip=el.closest('figure').querySelector('.tip');
el.addEventListener('mouseenter',()=>{{const o=JSON.parse(el.dataset.tip);tip.innerHTML='<b>'+o.n+'</b><br>Indice '+o.s+' · '+o.c+' $ par tâche'+(o.p?' · '+o.p:'');tip.style.display='block'}});
el.addEventListener('mousemove',e=>{{const r=tip.parentElement.getBoundingClientRect();tip.style.left=(e.clientX-r.left+12)+'px';tip.style.top=(e.clientY-r.top-8)+'px'}});
el.addEventListener('mouseleave',()=>tip.style.display='none')}});
show((location.hash||'#home').slice(1)||'home');
window.addEventListener('hashchange',()=>show((location.hash||'#home').slice(1)||'home'));
const rb=document.getElementById('runbtn'),rs=document.getElementById('runstate');let poll=null;
function fmt(t){{if(!t)return'';const d=new Date(t.replace(/^\\w+ /,''));return isNaN(d)?t:d.toLocaleString('fr-FR',{{dateStyle:'short',timeStyle:'short'}})}}
async function state(){{try{{const r=await fetch('/api/status',{{cache:'no-store'}});const o=await r.json();
if(o.running){{rb.disabled=true;rs.textContent='Cycle en cours — '+(o.step||'démarrage')}}
else{{rb.disabled=false;rs.textContent=o.finished?('Dernier cycle complet : '+fmt(o.finished)+(o.result&&o.result!=='success'?' (échec)':'')):''; if(poll){{clearInterval(poll);poll=null;if(o.result==='success')setTimeout(()=>location.reload(),20000)}}}}
if(o.running&&!poll)poll=setInterval(state,15000)}}catch(e){{rs.textContent='Statut indisponible'}}}}
rb.onclick=async()=>{{if(!confirm('Lancer maintenant le cycle complet ? Collecte des classements, recalcul, analyse par le modèle économique, notifications et republication de cette page (20 à 60 minutes).'))return;
rb.disabled=true;rs.textContent='Lancement…';try{{const r=await fetch('/api/run',{{method:'POST'}});const o=await r.json();rs.textContent=o.message||'';}}catch(e){{rs.textContent='Échec du lancement'}}setTimeout(state,1500)}};
state();
document.querySelectorAll('form.planform').forEach(f=>{{const st=f.querySelector('.pf-state');
async function send(body){{st.textContent='Envoi…';try{{const r=await fetch('/api/plans',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});
const o=await r.json();st.textContent=r.ok?'Enregistré, la page se met à jour…':(o.error||'Refusé');if(r.ok)setTimeout(()=>location.reload(),45000)}}catch(e){{st.textContent='Échec de l’envoi'}}}}
f.onsubmit=e=>{{e.preventDefault();const d=Object.fromEntries(new FormData(f));const id=f.dataset.id||d.sub_id;delete d.sub_id;
d.models=(d.models||'').split(',').map(x=>x.trim()).filter(Boolean);send({{action:'set',sub_id:id,fields:d}})}};
const r=f.querySelector('.pf-retire');if(r)r.onclick=()=>{{if(confirm('Résilier ce plan ? Il sortira de tes abonnements (gardé dans l’historique).'))send({{action:'retire',sub_id:f.dataset.id}})}}}});
</script></body></html>"""

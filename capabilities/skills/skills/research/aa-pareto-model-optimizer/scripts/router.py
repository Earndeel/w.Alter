#!/usr/bin/env python3
"""Router: 3 intelligence levels from the AA Pareto optimum + conditional
Design Arena escalation.

Philosophy (per Monsieur):
  1. The AA Intelligence Pareto frontier defines THREE intelligence levels:
     L1 standard  — value anchor (best $/score on the frontier)
     L2 high      — mid ladder tier
     L3 max       — quality ceiling
  2. DEFAULT: route to the model of the required level (cheapest sufficient).
  3. CONDITIONAL ESCALATION: only when the specific action needs a domain
     skill (frontend, 3D, game, dataviz, svg, fullstack build, ...), take the
     BEST model in that domain per Design Arena human preference — and report
     the cost delta so the escalation is a conscious choice.

Consumes the fresh artifacts from the pipeline:
  latest.json, designarena.json, model_profiles.json

Outputs:
  router_matrix.json  (levels + design-domain leaders + per-level decisions)

CLI:
  python3 router.py                # full report
  python3 router.py "landing page" # resolve need -> default + escalation
  python3 router.py --level 2 "landing page"   # force intelligence level
  python3 router.py --list-domains # show design domains + leaders
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Intelligence level bands (AA Intelligence Index). Models are picked from the
# pragmatic frontier inside each band: highest score for L2/L3, best
# score-per-dollar for L1 unless overridden by --anchor-slug.
# ---------------------------------------------------------------------------
INTELLIGENCE_LEVELS = [
    {"level": 1, "label": "standard", "min_intel": 40.0, "max_intel": 55.0,
     "pick": "value", "description": "Ancre Pareto — volume quotidien, tâches simples"},
    {"level": 2, "label": "high", "min_intel": 55.0, "max_intel": 61.0,
     "pick": "score", "description": "Palier intermédiaire — raisonnement poussé"},
    {"level": 3, "label": "max", "min_intel": 61.0, "max_intel": 200.0,
     "pick": "score", "description": "Plafond de qualité — tâches critiques"},
]

# ---------------------------------------------------------------------------
# Design domains -> Design Arena categories used for the escalation table.
# domain key matches the design_categories labels in model_profiles.json.
# ---------------------------------------------------------------------------
DESIGN_DOMAINS = [
    {"domain": "frontend", "label": "Frontend / Website / Landing",
     "keywords": ["landing", "website", "frontend", "ui", "html", "css", "site web",
                  "page", "interface", "responsive", "saas site", "portfolio", "vitrine",
                  "web", "design"],
     "categories": ["Website", "UI Component", "Overall"]},
    {"domain": "3d", "label": "3D / WebGL / Scene",
     "keywords": ["3d", "three.js", "webgl", "scene", "modeling", "3d design"],
     "categories": ["3D", "Overall"]},
    {"domain": "gamedev", "label": "Game Dev (canvas/HTML5)",
     "keywords": ["game", "gamedev", "canvas", "playable", "2d game", "interactive game"],
     "categories": ["Game Dev", "Overall"]},
    {"domain": "dataviz", "label": "Data Visualization / Dashboard",
     "keywords": ["dataviz", "chart", "dashboard", "graph", "visualization", "visualisation",
                  "plot", "d3", "chartjs"],
     "categories": ["Data Viz", "Overall"]},
    {"domain": "svg", "label": "SVG / Vector art",
     "keywords": ["svg", "vector", "icon", "logo"],
     "categories": ["SVG", "Overall"]},
    {"domain": "brand", "label": "Logo / Graphic / Brand",
     "keywords": ["logo", "graphic", "brand", "visual identity", "poster", "banner"],
     "categories": ["Logo", "Graphic Design", "Overall"]},
    {"domain": "build", "label": "Full-stack / Web app / Mobile build",
     "keywords": ["full-stack", "fullstack", "webapp", "mobile app", "react app", "saas",
                  "app build", "backend app", "crud"],
     "categories": ["Agent Full-Stack", "Agent Web Apps", "Agent Mobile", "Overall"]},
    {"domain": "slides", "label": "Slides / Deck / Presentation",
     "keywords": ["slide", "deck", "presentation", "ppt", "pitch"],
     "categories": ["Overall"]},
]


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home  # type: ignore
        return Path(get_hermes_home())
    except Exception:
        configured = os.environ.get("HERMES_HOME")
        if configured:
            return Path(configured).expanduser()
        return Path.home() / ".hermes"


def default_output_dir() -> Path:
    return hermes_home() / "cache" / "aa-pareto"


def normalize_slug(model_id: str) -> str:
    return (model_id or "").lower().replace(".", "-").replace("_", "-").strip()


def load_data(out_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    aa_path, da_path, prof_path = (
        out_dir / "latest.json", out_dir / "designarena.json", out_dir / "model_profiles.json")
    missing = [p.name for p in (aa_path, da_path, prof_path) if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing: " + ", ".join(missing) + ". Run refresh.py, collect_designarena.py, "
            "build_model_profiles.py first (or the cron wrapper).")
    return (json.loads(aa_path.read_text()),
            json.loads(da_path.read_text()),
            json.loads(prof_path.read_text()))


def ladder_knee(tiers: list[dict[str, Any]], min_drop: float = 2.0) -> dict[str, Any]:
    """Return the upgrade-ladder tier just before the sharpest fall in marginal return.

    Each tier after the anchor carries ``marginal_score_per_dollar_from_previous``. The knee is the
    tier ``i`` maximising ``m[i] / m[i+1]``: buying past it costs disproportionately more per point.
    The fall must be at least ``min_drop``x (same 2.0 default as the standout knee strength);
    otherwise returns stay roughly constant all the way up and the top tier is the sweet spot.
    With fewer than two upgrade segments there is no knee; fall back to the first upgrade or anchor.
    """
    ups = [t for t in tiers[1:] if (t.get("marginal_score_per_dollar_from_previous") or 0) > 0]
    if len(ups) < 2:
        return ups[0] if ups else tiers[0]
    m = [t["marginal_score_per_dollar_from_previous"] for t in ups]
    i = max(range(len(m) - 1), key=lambda k: m[k] / m[k + 1])
    return ups[i] if m[i] / m[i + 1] >= min_drop else ups[-1]


def build_intelligence_levels(aa: dict[str, Any]) -> list[dict[str, Any]]:
    """Pick the frontier model for each level from the AA Pareto upgrade ladder.

    Uses the ladder when present (it already encodes the strongest knee):
      L1 = value_anchor (best value on the frontier)
      L2 = knee: last tier before the sharpest fall in marginal score per dollar
      L3 = quality_ceiling (max score)
    Falls back to score bands when the ladder is missing.
    """
    ladder = aa["frontiers"]["intelligence_aa"]["upgrade_ladder"]
    tiers = ladder.get("tiers") or []
    if tiers:
        anchor = next((t for t in tiers if t.get("tier_type") == "value_anchor"), tiers[0])
        ceiling = ladder.get("quality_ceiling") or tiers[-1]
        mid = ladder_knee(tiers)

        def lvl_entry(level: int, label: str, desc: str, t: dict[str, Any]) -> dict[str, Any]:
            return {
                "level": level, "label": label, "description": desc,
                "min_intel": None, "model": t.get("model"), "slug": t.get("slug"),
                "intel_index": round(t.get("score") or 0, 2),
                "cost_per_task_usd": t.get("cost_per_task_usd"),
                "score_per_dollar": round((t.get("score") or 0) / (t.get("cost_per_task_usd") or 1e-9), 1)
                if t.get("cost_per_task_usd") else None,
            }

        return [
            lvl_entry(1, "standard", "Ancre Pareto (value_anchor) — volume quotidien, tâches simples", anchor),
            lvl_entry(2, "high", "Coude de l'échelle (sweet spot) — raisonnement poussé", mid),
            lvl_entry(3, "max", "Plafond qualité (quality_ceiling) — tâches critiques", ceiling),
        ]

    # Fallback: band scoring on the pragmatic frontier
    frontier = aa["frontiers"]["intelligence_aa"]["pragmatic_frontier"]
    slots = [[lvl, []] for lvl in INTELLIGENCE_LEVELS]
    for lvl, bucket in slots:
        for row in frontier:
            s = row.get("score") or 0
            c = row.get("cost_per_task_usd")
            if c is None or c <= 0:
                continue
            if lvl["min_intel"] <= s < lvl["max_intel"]:
                bucket.append(row)
    levels = []
    for lvl, bucket in slots:
        if not bucket:
            continue
        if lvl["pick"] == "value":
            chosen = max(bucket, key=lambda r: (r.get("score") or 0) / (r.get("cost_per_task_usd") or 1e-9))
        else:
            chosen = max(bucket, key=lambda r: r.get("score") or 0)
        levels.append({
            "level": lvl["level"],
            "label": lvl["label"],
            "description": lvl["description"],
            "min_intel": lvl["min_intel"],
            "model": chosen.get("model"),
            "slug": chosen.get("slug"),
            "intel_index": round(chosen.get("score") or 0, 2),
            "cost_per_task_usd": chosen.get("cost_per_task_usd"),
            "score_per_dollar": round((chosen.get("score") or 0) / (chosen.get("cost_per_task_usd") or 1e-9), 1),
        })
    return levels


def build_domain_leaders(da: dict[str, Any]) -> list[dict[str, Any]]:
    """Best model per design domain from Design Arena (human preference).
    Rows carry modelId, elo, win_rate, battles, rank within that category.
    """
    cat_key = {
        "Website": "website", "UI Component": "uicomponent", "3D": "3d",
        "Game Dev": "gamedev", "Data Viz": "dataviz", "SVG": "svg",
        "Graphic Design": "graphicdesign", "Logo": "logo", "Overall": "allcategories",
        "Agent Full-Stack": "agents/fullstack", "Agent Web Apps": "agents/agon_webapps",
        "Agent Mobile": "agents/mobileapps",
    }
    leaders = []
    for dom in DESIGN_DOMAINS:
        # Primary = first category listed for the domain; alternatives looked up
        # in order. "Overall" is only a fallback when no specific category exists.
        specific = [c for c in dom["categories"] if c != "Overall"]
        order = specific + ([c for c in dom["categories"] if c == "Overall"] if not specific else [])
        best = None
        for label in order:
            rows = da["categories"].get(cat_key.get(label, ""), [])
            rows = [r for r in rows if r.get("elo") is not None]
            if not rows:
                continue
            rows.sort(key=lambda r: r["elo"], reverse=True)
            r0 = rows[0]
            best = {
                "model": r0.get("model"),
                "elo": r0.get("elo"),
                "win_rate": r0.get("win_rate"),
                "battles": r0.get("battles"),
                "rank": 1,
                "category": label,
            }
            break
        if best:
            best["domain"] = dom["domain"]
            best["label"] = dom["label"]
            best["keywords"] = dom["keywords"]
            leaders.append(best)
        else:
            leaders.append({
                "domain": dom["domain"], "label": dom["label"], "keywords": dom["keywords"],
                "model": None, "elo": None, "category": None,
            })
    return leaders


def enrich_with_aa_cost(leaders: list[dict[str, Any]], aa: dict[str, Any]) -> None:
    """Attach AA cost-per-task and intel index to each domain leader (base slug)."""
    by_slug: dict[str, dict[str, Any]] = {}
    for row in aa.get("data", []):
        by_slug.setdefault(normalize_slug(row.get("slug", "")), row)
    for lead in leaders:
        if not lead.get("model"):
            continue
        aa_row = by_slug.get(normalize_slug(lead["model"]))
        lead["aa_cost_per_task_usd"] = aa_row.get("aa_cost_per_task_intelligence_usd") if aa_row else None
        lead["aa_intel_index"] = aa_row.get("intelligence_index") if aa_row else None
        # Models absent from AA (image/video generators, e.g. gpt-image-2 in the
        # brand domain) are outside the text-LLM pool; flag them.
        lead["in_llm_pool"] = lead["aa_cost_per_task_usd"] is not None


def resolve_domain(need: str) -> str | None:
    """Map free-form need to a design domain; None if no domain skill required.
    Specific keywords outrank generic ones (length-weighted hits)."""
    needle = need.lower()
    best_domain, best_hits = None, 0
    for dom in DESIGN_DOMAINS:
        hits = sum(len(kw) for kw in dom["keywords"] if kw in needle)
        if hits > best_hits:
            best_domain, best_hits = dom["domain"], hits
    return best_domain if best_hits > 0 else None


def fmt_cost(v: float | None) -> str:
    if v is None:
        return "n/a"
    if v == 0:
        return "$0"
    if v < 0.001:
        return f"${v:.5f}"
    if v < 0.1:
        return f"${v:.4f}"
    if v < 1:
        return f"${v:.3f}"
    return f"${v:.2f}"


def print_full_report(levels: list[dict[str, Any]], leaders: list[dict[str, Any]]) -> None:
    print("=== 3 NIVEAUX D'INTELLIGENCE (optimum Pareto AA) ===")
    for lvl in levels:
        print(f"  L{lvl['level']} [{lvl['label']:9s}] {lvl['model']:38s} intel={lvl['intel_index']:5.2f} "
              f"cost/task={fmt_cost(lvl['cost_per_task_usd'])}  ({lvl['description']})")
    print("\n=== ESCALADE DESIGN (meilleur par domaine, Design Arena) ===")
    for lead in leaders:
        if not lead.get("model"):
            continue
        extra = ""
        if lead.get("aa_cost_per_task_usd") is not None:
            extra = f" aa_cost={fmt_cost(lead['aa_cost_per_task_usd'])}"
        else:
            extra = " (hors pool LLM — générateur image/vidéo)"
        print(f"  {lead['domain']:10s} {lead['label']:44s} -> {lead['model']:28s} "
              f"elo={lead['elo']} (rank #{lead['rank']}){extra}")


def print_decision(need: str, levels: list[dict[str, Any]],
                   leaders: list[dict[str, Any]], force_level: int | None,
                   prof: dict[str, Any] | None = None) -> None:
    domain = resolve_domain(need)
    print(f"\nBesoin : '{need}'")
    if domain:
        print(f"  → Domaine design requis : {domain} ({next(d['label'] for d in DESIGN_DOMAINS if d['domain'] == domain)})")
    else:
        print("  → Aucun domaine design spécifique requis : routage purement AA.")

    # Default: cheapest sufficient intelligence level.
    lvl = next((l for l in levels if l["level"] == (force_level or 1)), levels[0])
    print(f"\n[DÉFAUT] Niveau L{lvl['level']} ({lvl['label']}) — {lvl['model']} "
          f"intel={lvl['intel_index']} cost/task={fmt_cost(lvl['cost_per_task_usd'])}")

    if domain:
        lead = next((l for l in leaders if l["domain"] == domain), None)
        if lead and lead.get("model"):
            cost_lead = fmt_cost(lead.get("aa_cost_per_task_usd"))
            extra = ""
            if lead.get("aa_cost_per_task_usd") is not None and lvl.get("cost_per_task_usd"):
                ratio = lead["aa_cost_per_task_usd"] / lvl["cost_per_task_usd"]
                extra = f" (x{ratio:.1f} le coût du défaut)"
            print(f"[ESCALADE {domain}] Meilleur du domaine (Design Arena) : {lead['model']} "
                  f"elo={lead['elo']} ({lead['category']}) — {cost_lead}{extra}")
            if lvl["model"] == lead["model"]:
                print("  → Le modèle par défaut est DÉJÀ le meilleur du domaine : pas d'escalade.")
            else:
                print("  → Escalade conditionnelle activée (le besoin exige ce domaine).")
            # Compromise: best design model within the DEFAULT level's budget
            if prof is not None and lead.get("aa_cost_per_task_usd") is not None \
                    and lvl["cost_per_task_usd"] is not None and lead["aa_cost_per_task_usd"] > lvl["cost_per_task_usd"]:
                dom_obj = next(d for d in DESIGN_DOMAINS if d["domain"] == domain)
                cat_labels = [c for c in dom_obj["categories"] if c != "Overall"]
                # Budget = the default level's own current task cost (never a pinned constant).
                budget = lvl["cost_per_task_usd"]
                if budget is not None:
                    cands = []
                    for p in prof.get("profiles", []):
                        cost = p.get("aa_cost_per_task_intelligence_usd")
                        if cost is None or cost > budget:
                            continue
                        da_block = p.get("design_arena", {})
                        best_elo = None
                        for lab in cat_labels:
                            e = da_block.get(lab, {}).get("elo")
                            if e is not None:
                                best_elo = e if best_elo is None else max(best_elo, e)
                        if best_elo is not None:
                            cands.append((best_elo, p.get("model"), cost))
                    if cands:
                        cands.sort(reverse=True)
                        e, m, c = cands[0]
                        print(f"[COMPROMIS] Meilleur design dans le budget L{lvl['level']} "
                              f"(≤ {fmt_cost(budget)}) : {m} design_elo={e} — {fmt_cost(c)}")
        else:
            print(f"[ESCALADE {domain}] Pas de leader Design Arena publié pour ce domaine.")

    print(f"\nNiveaux disponibles : " + ", ".join(
        f"L{l['level']} {l['model']} ({l['intel_index']})" for l in levels))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("need", nargs="?", help="Free-form need, e.g. 'landing page'")
    parser.add_argument("--level", type=int, choices=[1, 2, 3],
                        help="Force intelligence level for the default route")
    parser.add_argument("--list-domains", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    out_dir = default_output_dir()
    aa, da, prof = load_data(out_dir)

    levels = build_intelligence_levels(aa)
    leaders = build_domain_leaders(da)
    enrich_with_aa_cost(leaders, aa)

    if args.list_domains:
        for lead in leaders:
            print(f"  {lead['domain']:10s} {lead['label']:44s} -> {lead.get('model') or '—'} "
                  f"elo={lead.get('elo') or '—'}")
        return

    if args.need:
        print_decision(args.need, levels, leaders, args.level, prof)
    else:
        print_full_report(levels, leaders)

    # Persist artifacts
    doc = {
        "generated_at": da.get("generated_at"),
        "aa_generated_at": aa.get("generated_at"),
        "intelligence_levels": levels,
        "design_domains": leaders,
    }
    (out_dir / "router_matrix.json").write_text(json.dumps(doc, indent=1))
    with (out_dir / "router_matrix.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["kind", "level_or_domain", "model", "metric", "value", "cost_per_task_usd"])
        for lvl in levels:
            w.writerow(["level", lvl["level"], lvl["model"], "intel_index",
                        lvl["intel_index"], lvl["cost_per_task_usd"]])
        for lead in leaders:
            w.writerow(["design_domain", lead["domain"], lead.get("model"), "elo",
                        lead.get("elo"), lead.get("aa_cost_per_task_usd")])
    if not args.quiet:
        print(f"\nArtifacts: {out_dir / 'router_matrix.json'}, {out_dir / 'router_matrix.csv'}")


if __name__ == "__main__":
    main()
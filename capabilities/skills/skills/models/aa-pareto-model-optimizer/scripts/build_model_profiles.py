#!/usr/bin/env python3
"""Build per-model competence profiles joining AA Pareto + Design Arena.

For every AA model that matches a Design Arena model, output a profile with:

- AA side: Intelligence Index and its matching AA cost per task;
- Design Arena side (models arena + agentic-build arena): per-category
  competence scores — Elo, win rate, battles, plus the model's rank within
  that category (1 = highest Elo).

Slug matching: AA slugs carry reasoning-tier suffixes (``gpt-5-6-luna-high``)
while Design Arena keys models at the base level (``gpt-5.6-luna``). We match
on the normalized base slug (dots/underscores -> hyphens, tier suffixes
stripped). A model that AA tracks per-tier therefore inherits the base model's
full competence profile once, labelled with the base name.

Outputs:
    $HERMES_HOME/cache/aa-pareto/model_profiles.json
    $HERMES_HOME/cache/aa-pareto/model_profiles.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

TIER_SUFFIXES = (
    "-low", "-medium", "-high", "-xhigh", "-max",
    "-non-reasoning", "-thinking", "-preview",
)
# Category -> human label used for CSV columns (keep stable order).
CATEGORY_LABELS = [
    ("allcategories", "Overall"),
    ("website", "Website"),
    ("uicomponent", "UI Component"),
    ("gamedev", "Game Dev"),
    ("dataviz", "Data Viz"),
    ("3d", "3D"),
    ("svg", "SVG"),
    ("graphicdesign", "Graphic Design"),
    ("logo", "Logo"),
    ("agents/fullstack", "Agent Full-Stack"),
    ("agents/webapps", "Agent Web Apps"),
    ("agents/mobileapps", "Agent Mobile"),
    ("agents/nativeapps", "Agent Native"),
    ("agents/agentic_3d", "Agent 3D"),
    ("agents/agon_dataviz", "Agent Data Viz"),
    ("agents/agon_html", "Agent HTML"),
]

TIER_RE = re.compile(r"-(low|medium|high|xhigh|max|non-reasoning|thinking|preview)$")


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


def base_slug(model_id: str) -> str:
    """Strip reasoning-tier suffixes so tiered AA slugs join base DA models."""
    slug = normalize_slug(model_id)
    changed = True
    while changed:
        changed = False
        for suffix in TIER_SUFFIXES:
            if slug.endswith(suffix) and not slug.endswith(suffix + "-"):
                slug = slug[: -len(suffix)]
                changed = True
    return slug


def build_ranks(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Rank (1-based) by Elo descending; ties share the best rank."""
    ranked = sorted(rows, key=lambda r: r.get("elo") if r.get("elo") is not None else -1, reverse=True)
    ranks: dict[str, int] = {}
    prev_elo = None
    prev_rank = 0
    for idx, row in enumerate(ranked, start=1):
        elo = row.get("elo")
        if elo is None:
            continue
        if prev_elo is not None and abs(elo - prev_elo) < 1e-9:
            ranks[row["slug_norm"]] = prev_rank
        else:
            ranks[row["slug_norm"]] = idx
            prev_rank = idx
            prev_elo = elo
    return ranks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    output_dir = args.output_dir or default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    aa_path = output_dir / "latest.json"
    da_path = output_dir / "designarena.json"
    if not aa_path.is_file() or not da_path.is_file():
        raise FileNotFoundError(
            f"Need both {aa_path} and {da_path}; run refresh.py + collect_designarena.py first"
        )

    aa = json.loads(aa_path.read_text())
    da = json.loads(da_path.read_text())

    aa_rows: dict[str, dict[str, Any]] = {}
    for row in aa.get("data", []):
        slug = row.get("slug")
        if not slug:
            continue
        aa_rows[slug] = row
    aa_base_index: dict[str, list[str]] = {}
    for slug in aa_rows:
        aa_base_index.setdefault(base_slug(slug), []).append(slug)

    # Competence matrix: category -> slug_norm -> row
    categories = da.get("categories", {})
    competence: dict[str, dict[str, dict[str, Any]]] = {}
    ranks: dict[str, dict[str, int]] = {}
    for cat, rows in categories.items():
        cat_rows = [r for r in rows if r.get("elo") is not None]
        competence[cat] = {r["slug_norm"]: r for r in cat_rows}
        ranks[cat] = build_ranks(cat_rows)

    registry = da.get("registry", {})

    # Build one profile per AA slug (tiered slugs inherit base-level competence).
    profiles: list[dict[str, Any]] = []
    for aa_slug, row in aa_rows.items():
        base = base_slug(aa_slug)
        da_base = registry.get(base)
        da_rows = competence.get("allcategories", {}).get(base)
        profile: dict[str, Any] = {
            "aa_slug": aa_slug,
            "model": row.get("name") or aa_slug,
            "base_model": da_base.get("display_name") if da_base else None,
            "provider": (da_base or {}).get("provider") or row.get("provider"),
            "da_matched": da_base is not None,
            "intelligence_index": row.get("intelligence_index"),
            "aa_cost_per_task_intelligence_usd": row.get("aa_cost_per_task_intelligence_usd"),
            "design_arena": {},
        }
        if da_base:
            for cat, label in CATEGORY_LABELS:
                crow = competence.get(cat, {}).get(base)
                if not crow:
                    continue
                profile["design_arena"][label] = {
                    "elo": crow.get("elo"),
                    "win_rate": crow.get("win_rate"),
                    "battles": crow.get("battles"),
                    "rank": ranks.get(cat, {}).get(base),
                    "category": label,
                }
        # Competence summary: competence "present" if matched in that category
        present = [v["category"] for v in profile["design_arena"].values()]
        profile["design_arena_present_categories"] = present
        best = None
        if present:
            best = max(
                profile["design_arena"].values(),
                key=lambda v: (v.get("elo") or -1),
            )
            profile["design_arena_best_category"] = best["category"]
            profile["design_arena_best_elo"] = best["elo"]
            profile["design_arena_best_rank"] = best["rank"]
        profiles.append(profile)

    profiles.sort(key=lambda p: (p["da_matched"], -(p.get("intelligence_index") or 0)))

    doc = {
        "generated_at": da.get("generated_at"),
        "aa_generated_at": aa.get("generated_at"),
        "count_aa": len(aa_rows),
        "count_da_matched": sum(1 for p in profiles if p["da_matched"]),
        "profiles": profiles,
    }
    out_path = output_dir / "model_profiles.json"
    out_path.write_text(json.dumps(doc, indent=1))

    # CSV: one row per DA-matched profile (tiered AA slugs inherit base).
    csv_path = output_dir / "model_profiles.csv"
    label_cols = ["Overall", "Website", "UI Component", "Game Dev", "Data Viz", "3D",
                  "SVG", "Graphic Design", "Logo", "Agent Full-Stack", "Agent Web Apps",
                  "Agent Mobile", "Agent Native", "Agent 3D", "Agent Data Viz", "Agent HTML"]
    with csv_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["aa_slug", "model", "provider", "da_matched",
                         "intelligence_index", "aa_cost_per_task_intelligence_usd",
                         "design_arena_best_category", "design_arena_best_elo",
                         *[f"{c} elo" for c in label_cols],
                         *[f"{c} rank" for c in label_cols]])
        for p in profiles:
            da_map = {v["category"]: v for v in p["design_arena"].values()}
            writer.writerow([
                p["aa_slug"], p["model"], p["provider"], p["da_matched"],
                p["intelligence_index"],
                p["aa_cost_per_task_intelligence_usd"],
                p.get("design_arena_best_category"), p.get("design_arena_best_elo"),
                *[(da_map.get(c) or {}).get("elo") for c in label_cols],
                *[(da_map.get(c) or {}).get("rank") for c in label_cols],
            ])

    matched = sum(1 for p in profiles if p["da_matched"])
    if not args.quiet:
        print(f"model_profiles: {len(profiles)} AA rows, {matched} matched to Design Arena")
        print(f"  -> {out_path}")
        print(f"  -> {csv_path}")


if __name__ == "__main__":
    main()
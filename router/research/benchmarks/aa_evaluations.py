"""Artificial Analysis evaluations and domain indexes, one score per model x reasoning level: specialised domains (medical HealthBench,
legal Harvey LAB, finance tau3-Banking, science CritPt / GPQA / SciCode / HLE), vision (MMMU-Pro), 3D (AA-3D Elo),
long context (AA-LCR), instruction following (IFBench), agents (tau2, Terminal-Bench Hard, GDPval, APEX-Agents),
knowledge reliability (AA-Omniscience), coding (LiveCodeBench), cybersecurity (AA Cyber Index); and the domain
indexes of artificialanalysis.ai/indexes (engineering, economics, finance & accounting, healthcare, legal, strategy &
ops) with their cost and time per task.

The model pages carry AA's whole language-model catalogue with every evaluation field; an evaluation page carries the
same objects for the models it features (HealthBench is only there). Both are read from their Next.js data, merged by
slug — no browser. Stored as fractions by AA, kept here as published; analysis.parse puts them on 0-100."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from walter_router.research.benchmarks.aa import (AA_MODEL_URL, ANCHORS, RSC_PUSH_PATTERN, decode_rsc_string, index_version,
                                                  strip_rsc_prefix, updates)
from walter_router.research.web import fetch_text, now

EVAL_URL = "https://artificialanalysis.ai/evaluations/{}"
# router key -> (AA field, evaluation page slug, unit). Fractions are multiplied by 100 at parse time ('pct').
EVALS: dict[str, tuple[str, str, str]] = {
    "healthbench": ("healthbench", "healthbench", "pct"),
    "healthbench_pro": ("healthbenchProfessional", "healthbench-professional", "pct"),
    "harvey_lab": ("harveyLab", "harvey-lab-aa", "pct"),
    "tau_banking": ("tauBanking", "tau3-banking", "pct"),
    "critpt": ("critpt", "critpt", "pct"),
    "gpqa": ("gpqa", "gpqa-diamond", "pct"),
    "scicode": ("scicode", "scicode", "pct"),
    "hle": ("hle", "humanitys-last-exam", "pct"),
    "mmmu_pro": ("mmmuPro", "mmmu-pro", "pct"),
    "aa_3d": ("aa3dElo", "aa-3d", "elo"),
    "lcr": ("lcr", "artificial-analysis-long-context-reasoning", "pct"),
    "ifbench": ("ifbench", "ifbench", "pct"),
    "global_mmlu": ("globalMmluLiteScore", "global-mmlu-lite", "pct"),
    "tau2": ("tau2", "tau2-bench", "pct"),
    "terminalbench_hard": ("terminalbenchHard", "terminalbench-hard", "pct"),
    "gdpval": ("gdpvalNormalized", "gdpval-aa", "pct"),
    "apex_agents": ("apexAgents", "apex-agents-aa", "pct"),
    "omniscience": ("omniscience", "omniscience", "index"),
    "livecodebench": ("livecodebench", "livecodebench", "pct"),
    "cyber": ("cyberIndex", "artificial-analysis-cyber-index", "index"),
}
# AA domain indexes (artificialanalysis.ai/indexes, 2026-10): one weighted index per profession on AA's frontier models,
# with its own cost and time per task. Read from each index page (initialModels).
INDEX_URL = "https://artificialanalysis.ai/indexes/{}"
INDEXES = {"idx_engineering": "engineering", "idx_economics": "economics", "idx_finance": "finance-and-accounting",
           "idx_medical": "healthcare-and-medical", "idx_legal": "legal", "idx_strategy_ops": "strategy-and-ops"}
# evaluations whose scores are not (or not all) in the model-page catalogue: read from their own page as well
PAGE_ONLY = ("healthbench", "healthbench_pro", "cyber")
MIN_MODELS = 300


def _objects(page: str) -> list[dict[str, Any]]:
    """Every model object (has a slug and at least one evaluation field) in the page's flight data."""
    fields = {f for f, _, _ in EVALS.values()}
    out: list[dict[str, Any]] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            if x.get("slug") and fields & x.keys():
                out.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for m in RSC_PUSH_PATTERN.finditer(page):
        decoded = strip_rsc_prefix(decode_rsc_string(m.group(1)))
        for line in decoded.split("\n"):
            line = re.sub(r"^[0-9a-z]+:", "", line, count=1)
            try:
                walk(json.loads(line))
            except ValueError:
                continue
    return out


def _index_models(page: str) -> list[dict[str, Any]]:
    """The initialModels list of an AA index page: weightedIndex, costPerTask.total, timePerTaskSeconds per model."""
    out: list[dict[str, Any]] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            if isinstance(x.get("initialModels"), list):
                out.extend(m for m in x["initialModels"] if isinstance(m, dict) and m.get("slug"))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for m in RSC_PUSH_PATTERN.finditer(page):
        decoded = strip_rsc_prefix(decode_rsc_string(m.group(1)))
        for line in decoded.split("\n"):
            try:
                walk(json.loads(re.sub(r"^[0-9a-z]+:", "", line, count=1)))
            except ValueError:
                continue
    return out


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def merge(objects: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """slug -> {name, slug, <key>: value} keeping the first non-null value of each evaluation."""
    models: dict[str, dict[str, Any]] = {}
    for o in objects:
        row = models.setdefault(o["slug"], {"slug": o["slug"], "name": o.get("shortName") or o.get("name") or o["slug"]})
        for key, (field, _, _) in EVALS.items():
            if row.get(key) is None and _num(o.get(field)) is not None:
                row[key] = _num(o.get(field))
    return models


def source_aa_eval() -> tuple[dict, datetime, str]:
    objects, used, errors = [], None, []
    for anchor in ANCHORS:
        try:
            found = _objects(fetch_text(AA_MODEL_URL.format(anchor)))
        except Exception as exc:  # noqa: BLE001 — next anchor
            errors.append(f"{anchor}: {exc}"[:160])
            continue
        if len({o["slug"] for o in found}) >= MIN_MODELS:
            objects, used = found, AA_MODEL_URL.format(anchor)
            break
        errors.append(f"{anchor}: {len(found)} objects")
    if not used:
        raise ValueError("AA evaluations: " + "; ".join(errors))
    pages = {}
    for key in PAGE_ONLY:
        url = EVAL_URL.format(EVALS[key][1])
        try:
            objects += _objects(fetch_text(url))
            pages[key] = url
        except Exception as exc:  # noqa: BLE001 — one page must not lose the others
            errors.append(f"{key}: {exc}"[:160])
    models = merge(objects)
    indexes: dict[str, list[dict[str, Any]]] = {}
    for key, slug in INDEXES.items():
        url = INDEX_URL.format(slug)
        try:
            rows = _index_models(fetch_text(url))
        except Exception as exc:  # noqa: BLE001 — one index page must not lose the others
            errors.append(f"{key}: {exc}"[:160])
            continue
        indexes[key] = [{"slug": m["slug"], "name": m.get("shortName") or m.get("name"), "index": _num(m.get("weightedIndex")),
                         "cost_per_task": _num((m.get("costPerTask") or {}).get("total")),
                         "time_per_task_s": _num(m.get("timePerTaskSeconds")), "sub_scores": m.get("subScores")}
                        for m in rows if _num(m.get("weightedIndex")) is not None]
        pages[key] = url
    badges = updates()
    doc = {"generated_at": now().isoformat(), "source_url": used, "pages": pages, "errors": errors,
           "evals": {k: {"field": f, "page": EVAL_URL.format(p), "unit": u} for k, (f, p, u) in EVALS.items()},
           "data": sorted(models.values(), key=lambda r: r["slug"]), "indexes": indexes,
           "versions": versions(badges, index_version()),
           "under_review": sorted(k for k, (_, p, _) in EVALS.items() if (badges.get(p) or {}).get("type") == "underReview")}
    return doc, now(), used


def versions(badges: dict[str, dict], intelligence: str | None) -> dict[str, str]:
    """Board -> version label (analysis.changes never compares a board across labels): the domain indexes are built
    on the Intelligence Index suite and follow its version (v5.0 re-based them, 2026-10-28); an evaluation AA marks
    'updated' (AA-Omniscience v1.1, Harvey LAB-AA v1.1…) carries AA's description of the update."""
    out = {f"aa_eval:{key}": f"intelligence {intelligence}" for key in INDEXES} if intelligence else {}
    for key, (_, page, _) in EVALS.items():
        badge = badges.get(page) or {}
        if badge.get("type") == "updated" and badge.get("description"):
            out[f"aa_eval:{key}"] = badge["description"]
    return out

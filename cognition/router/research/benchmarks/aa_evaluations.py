"""Artificial Analysis evaluations, one score per model x reasoning level: specialised domains (medical HealthBench,
legal Harvey LAB, finance tau3-Banking, science CritPt / GPQA / SciCode / HLE), vision (MMMU-Pro), 3D (AA-3D Elo),
long context (AA-LCR), instruction following (IFBench), multilingual (Global-MMLU-Lite), agents (tau2, Terminal-Bench
Hard, GDPval, APEX-Agents), knowledge reliability (AA-Omniscience), coding (LiveCodeBench).

The model pages carry AA's whole language-model catalogue with every evaluation field; an evaluation page carries the
same objects for the models it features (HealthBench is only there). Both are read from their Next.js data, merged by
slug — no browser. Stored as fractions by AA, kept here as published; analysis.parse puts them on 0-100."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from walter_router.research.benchmarks.aa import AA_MODEL_URL, ANCHORS, RSC_PUSH_PATTERN, decode_rsc_string, strip_rsc_prefix
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
}
# evaluations whose scores are not (or not all) in the model-page catalogue: read from their own page as well
PAGE_ONLY = ("healthbench", "healthbench_pro")
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
    doc = {"generated_at": now().isoformat(), "source_url": used, "pages": pages, "errors": errors,
           "evals": {k: {"field": f, "page": EVAL_URL.format(p), "unit": u} for k, (f, p, u) in EVALS.items()},
           "data": sorted(models.values(), key=lambda r: r["slug"])}
    return doc, now(), used

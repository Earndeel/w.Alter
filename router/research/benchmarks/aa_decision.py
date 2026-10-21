"""AA Decision Index (decision models: intelligence, time and cost per 1M tasks)."""
from __future__ import annotations

import json
from datetime import datetime

from walter_router.research.web import fetch_text, now, rsc_text

# AA Decision Index (v1.0, 2026-10-13): decision models (typed answers + probabilities) and LLM references on
# AA-Omniscience-Decision, HLE-MultiChoice, When2Call and WildGuardTest; accuracy, time and cost per 1M tasks.
AA_DECISION_URL = "https://artificialanalysis.ai/evaluations/artificial-analysis-decision-index"


def aa_decision_rows(page: str) -> list[dict]:
    text = rsc_text(page)
    i = text.find('{"contestants":')
    if i < 0:
        raise ValueError("aa_decision: no contestants in page")
    rows, _ = json.JSONDecoder().raw_decode(text[i + len('{"contestants":'):])
    return rows


def source_aa_decision() -> tuple[dict, datetime, str]:
    rows = aa_decision_rows(fetch_text(AA_DECISION_URL))
    if len([r for r in rows if r.get("kind") == "decisionModel"]) < 5:
        raise ValueError(f"aa_decision: only {len(rows)} rows parsed")
    return {"rows": rows}, now(), AA_DECISION_URL

"""AA Speech-to-Text (WER, speed factor, price per model x host)."""
from __future__ import annotations

import json
import re
from datetime import datetime

from walter_router.research.web import _json_object, fetch_text, now, rsc_text

# Internal postes stt / rerank / embeddings (2026-10-16, the owner: « rajouter le reranking, embedding et STT »).
# AA Speech-to-Text: AA-WER index (lower = better, English datasets — AA publishes no French result), speed factor
# (x real time) and price per 1000 audio minutes, per model x host, from the page's chart download tables.
AA_STT_URL = "https://artificialanalysis.ai/speech-to-text"


AA_STT_TABLES = ("STT AA-WER vs Price", "STT AA-WER vs Speed Factor", "STT Speed Factor vs Price")


def aa_stt_rows(page: str) -> list[dict]:
    """One row per model x host of AA's Speech-to-Text page: the chart download tables (WER vs price, WER vs speed,
    speed vs price) joined on (Model, Provider); when the page carries no such table (since 2026-10-24), the host
    model objects of its flight data."""
    text = rsc_text(page)
    return _table_rows(text) or _host_model_rows(text)


# Host model object of the page data: {"id", "name", "displayName", ..., "pricePer1kMinutes", "host": {"name"},
# "performance": {"medianSpeedFactor"}, "aaWerIndex", ...}; displayName and host name = the old tables' Model, Provider.
_HOST_MODEL = re.compile(r'\{"id":"[0-9a-f-]{36}","name":"[^"]*","displayName":')


def _host_model_rows(text: str) -> list[dict]:
    merged: dict[tuple[str, str], dict] = {}
    for m in _HOST_MODEL.finditer(text):
        try:
            o = json.loads(_json_object(text, m.start()))
        except (ValueError, json.JSONDecodeError):
            continue
        if "aaWerIndex" not in o or not isinstance(o.get("host"), dict):
            continue
        host = o["host"].get("name") or ""
        row = merged.setdefault((o["displayName"], host), {"model": o["displayName"], "provider": host or None})
        for dst, value in (("wer", o.get("aaWerIndex")),
                           ("speed_factor", (o.get("performance") or {}).get("medianSpeedFactor")),
                           ("price_per_1k_min", o.get("pricePer1kMinutes"))):
            if value is not None:
                row[dst] = value
    return list(merged.values())


def _table_rows(text: str) -> list[dict]:
    merged: dict[tuple[str, str], dict] = {}
    for m in re.finditer(r'"downloadData":\{"data":\[', text):
        try:
            table = json.loads(_json_object(text, m.end() - len('{"data":[')))
        except (ValueError, json.JSONDecodeError):
            continue
        if table.get("fileName") not in AA_STT_TABLES:
            continue
        for r in table["data"]:
            row = merged.setdefault((r["Model"], r.get("Provider") or ""), {"model": r["Model"], "provider": r.get("Provider")})
            for src, dst in (("AA-WER Index", "wer"), ("Speed Factor", "speed_factor"), ("Price per 1k Min", "price_per_1k_min")):
                if r.get(src) is not None:
                    row[dst] = r[src]
    return list(merged.values())


def source_aa_stt() -> tuple[dict, datetime, str]:
    rows = aa_stt_rows(fetch_text(AA_STT_URL))
    if len([r for r in rows if r.get("wer") is not None]) < 20:
        raise ValueError(f"aa_stt: only {len(rows)} rows parsed")
    return {"rows": rows}, now(), AA_STT_URL

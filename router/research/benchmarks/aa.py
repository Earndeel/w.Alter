"""Artificial Analysis (intelligence + cost per task, multimodal arenas) and Design Arena, from the collection caches."""
from __future__ import annotations

import json
from datetime import datetime

from walter_router import instance
from walter_router.research.web import _parse_time

HERMES_HOME = instance.hermes_home()
CACHE = HERMES_HOME / "cache" / "aa-pareto"


def source_aa() -> tuple[dict, datetime, str]:
    doc = json.loads((CACHE / "latest.json").read_text())
    return doc, _parse_time(doc.get("generated_at")), "https://artificialanalysis.ai/"


def source_mm() -> tuple[dict, datetime, str]:
    doc = json.loads((CACHE / "multimodal_latest.json").read_text())
    return doc, _parse_time(doc.get("generated_at")), "https://artificialanalysis.ai/"


def source_da() -> tuple[dict, datetime, str]:
    doc = json.loads((CACHE / "designarena.json").read_text())
    return doc, _parse_time(doc.get("generated_at")), doc.get("source_url") or "https://www.designarena.ai/"

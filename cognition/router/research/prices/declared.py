"""Offers no API lists (web UIs, direct keys), declared by the owner."""
from __future__ import annotations

import json
from datetime import datetime

from walter_router import instance
from walter_router.research.web import now

DECLARED = instance.config_path("declared_offers.json")


def source_declared() -> tuple[dict, datetime, str]:
    doc = json.loads(DECLARED.read_text())
    return {"offers": doc["offers"]}, now(), str(DECLARED)

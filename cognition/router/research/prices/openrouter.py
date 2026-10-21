"""OpenRouter catalogue, all modalities, media prices from each model page."""
from __future__ import annotations

import html
import json
import time
from datetime import datetime

from walter_router.research.web import fetch_json, fetch_text, now

MEDIA_INTERFACES = ("image", "video", "audio", "music")


# Services priced per unit on their OpenRouter page (transcription per second / hour, rerank per search): the API's
# prompt "token" price of those models is that unit price, not a token price.
UNIT_PRICED_INTERFACES = MEDIA_INTERFACES + ("transcription", "rerank")


_OR_OUTPUTS = {"video": "video", "image": "image", "audio": "audio", "speech": "audio", "transcription": "transcription",
               "embeddings": "embedding", "rerank": "rerank"}


def _or_interface(model: dict) -> str:
    out = model.get("architecture", {}).get("output_modalities") or ["text"]
    if "lyria" in model["id"]:
        return "music"
    for modality, interface in _OR_OUTPUTS.items():
        if modality in out:
            return interface
    return "chat" if "text" in out else (out[0] if out else "chat")


OPENROUTER_URL = "https://openrouter.ai/api/v1/models?output_modalities=all"


def display_pricing(page: str) -> list | None:
    """The `displayPricing` array embedded in an OpenRouter model page (per-second / per-song / per-tier prices
    that the /models API reports as 0 for media models)."""
    text = html.unescape(page).replace('\\"', '"')
    i = text.find('"displayPricing":')
    if i < 0:
        return None
    j = text.index("[", i)
    depth = 0
    for k in range(j, len(text)):
        if text[k] == "[":
            depth += 1
        elif text[k] == "]":
            depth -= 1
            if depth == 0:
                return json.loads(text[j:k + 1])
    return None


def source_openrouter() -> tuple[dict, datetime, str]:
    doc = fetch_json(OPENROUTER_URL)
    if not doc.get("data"):
        raise ValueError("openrouter: empty catalogue")
    for m in doc["data"]:
        if _or_interface(m) not in UNIT_PRICED_INTERFACES or ":" in m["id"] or m["id"].startswith(("openrouter/", "~")):
            continue
        try:
            m["_display_pricing"] = display_pricing(fetch_text(f"https://openrouter.ai/{m['id']}"))
        except Exception as exc:  # noqa: BLE001 — a missing page leaves that model unpriced, not the run failed
            m["_display_pricing_error"] = f"{type(exc).__name__}: {exc}"[:200]
        time.sleep(0.3)
    return doc, now(), OPENROUTER_URL

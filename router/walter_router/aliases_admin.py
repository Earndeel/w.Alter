"""Validated name links (aliases) — how the 48 h analysis agent fixes naming gaps between sources
(e.g. OpenRouter `minimax/hailuo-3` = AA « MiniMax H3 »). A link is accepted only if the unscored id exists, the target
has measured scores, and it creates no chain or conflict. Every link keeps its evidence and can be removed."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from difflib import SequenceMatcher

from . import identity

MIN_SIMILARITY = 0.6  # below: a rename (Hailuo 3 = MiniMax H3) — accepted only with a source URL in the reason


def _read() -> dict:
    return json.loads(identity.AUTO_ALIASES.read_text())


def _write(doc: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=identity.AUTO_ALIASES.parent, suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, identity.AUTO_ALIASES)


def add(conn, key: str, model_id: str, reason: str, origin: str = "agent") -> dict:
    key, model_id = identity.canon(identity.slugify(key)), identity.canon(identity.slugify(model_id))
    if not reason or len(reason) < 15:
        raise ValueError("a link needs its evidence (reason >= 15 characters)")
    if key == model_id:
        raise ValueError("same id")
    if key in identity.MANUAL.get("*", {}):
        raise ValueError(f"{key} is already linked to {identity.MANUAL['*'][key]['model_id']}")
    if model_id in identity.MANUAL.get("*", {}):
        raise ValueError(f"{model_id} is itself an alias (no chains)")
    if not conn.execute("select 1 from models.canonical where model_id = %s", (key,)).fetchone():
        raise ValueError(f"unknown model id {key}")
    if conn.execute("select 1 from models.model_scores where model_id = %s", (key,)).fetchone():
        raise ValueError(f"{key} already has its own scores: not a naming gap")
    if not conn.execute("select 1 from models.model_scores where model_id = %s", (model_id,)).fetchone():
        raise ValueError(f"{model_id} has no scores: linking to it gains nothing")
    if SequenceMatcher(None, key, model_id).ratio() < MIN_SIMILARITY and "http" not in reason:
        raise ValueError("names too different (e.g. hailuo-3 / minimax-h3): cite the source URL proving it is the same model")
    doc = _read()
    doc["aliases"][key] = {"model_id": model_id, "reason": reason, "origin": origin,
                           "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _write(doc)
    identity.reload()
    return {"added": key, "model_id": model_id}


def remove(key: str) -> dict:
    doc = _read()
    gone = doc["aliases"].pop(identity.canon(identity.slugify(key)), None)
    _write(doc)
    identity.reload()
    return {"removed": key, "was": gone}


def listing() -> dict:
    return _read()["aliases"]

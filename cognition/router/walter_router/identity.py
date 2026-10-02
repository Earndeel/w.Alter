"""Deterministic model identities: every external key is normalised to (model_id, variant).

No fuzzy matching: two sources refer to the same model only when their normalised keys are equal or a
manual alias (aliases.json, each entry justified) says so. Unmatched keys simply stay their own model.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TIERS = ("non-reasoning", "minimal", "low", "medium", "high", "xhigh", "max")
VENDOR_PREFIXES = ("google-", "openai-", "anthropic-", "meta-", "microsoft-", "alibaba-", "bytedance-")
_TIER_SUFFIX = re.compile(r"-(" + "|".join(TIERS) + r")$")
_PAREN = re.compile(r"\(([^)]*)\)")
MANUAL = json.loads((Path(__file__).with_name("aliases.json")).read_text())


def slugify(text: str) -> str:
    text = text.strip().lower().lstrip("~")
    text = re.sub(r"[\s._/]+", "-", text)
    text = re.sub(r"[^a-z0-9-]", "", text)
    return re.sub(r"-+", "-", text).strip("-")


def _variant_from_paren(name: str) -> tuple[str, str]:
    """'Claude Opus 5.5 (xhigh with fallback)' -> ('Claude Opus 5.5', 'xhigh'); 'based on ...' notes are dropped."""
    variant = ""
    for inner in _PAREN.findall(name):
        inner = inner.strip().lower()
        if inner.startswith("based on") or not inner or slugify(inner).count("-") > 2:
            continue  # notes and alternate model names, not a variant
        variant = slugify(inner.replace("with fallback", ""))
    return _PAREN.sub("", name).strip(), variant


def normalize(namespace: str, key: str, name: str | None = None) -> tuple[str, str]:
    """Return (model_id, variant) for an external key of a namespace (aa | da | mm | openrouter | kie | codex)."""
    manual = MANUAL.get(namespace, {}).get(key)
    if manual:
        return manual["model_id"], manual.get("variant", "")
    variant = ""
    if namespace == "aa":
        # AA: slug carries the effort tier except for the default (max) row; the display name always does.
        _, variant = _variant_from_paren(name or "")
        base = _TIER_SUFFIX.sub("", key)
    elif namespace == "da":
        base = slugify(key)
        m = _TIER_SUFFIX.search(base)
        if m:
            base, variant = base[: m.start()], m.group(1)
    elif namespace == "mm":
        base, variant = _variant_from_paren(key)
        base = slugify(base)
    else:
        base = key.split(":")[0]
        if namespace == "openrouter" and "/" in base:
            base = base.split("/", 1)[1]
        if namespace == "kie" and "/" in base:
            base = base.rsplit("/", 1)[1]
        base = slugify(base)
    if namespace in ("kie", "mm"):
        for prefix in VENDOR_PREFIXES:
            if base.startswith(prefix):
                base = base[len(prefix):]
    alias = MANUAL.get("*", {}).get(base)
    if alias:
        base = alias["model_id"]
    return base, variant

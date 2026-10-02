"""Deterministic model identities: every external key is normalised to (model_id, variant).

No fuzzy matching: two sources refer to the same model only when their normalised keys are equal or a
manual alias (aliases.json, each entry justified) says so. Unmatched keys simply stay their own model.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TIERS = ("non-reasoning", "minimal", "low", "medium", "high", "xhigh", "max")
VENDOR_PREFIXES = ("google-", "openai-", "anthropic-", "meta-", "microsoft-", "alibaba-", "bytedance-",
                   "black-forest-labs-")
BENCHMARK_NAMESPACES = ("aa", "da", "mm", "arena", "bridgebench")
_TIER_SUFFIX = re.compile(r"-(" + "|".join(TIERS) + r")$")
_PAREN = re.compile(r"\(([^)]*)\)")
_GLUED = re.compile(r"(?<![a-z0-9])([a-z]{3,})(\d)")      # wan2-7 -> wan-2-7, flux1-1 -> flux-1-1 (not h3, v2, o1)
_DOT_ZERO = re.compile(r"(-\d+)-0(?=-[a-z]|$)")           # seedance-2-0-fast -> seedance-2-fast (not qwen-3-0-6b)
_RES_SUFFIX = re.compile(r"-(\d{3,4}p|\d(?:-\d)?k)$")    # leaderboard rows per output resolution
_DATE_SUFFIX = re.compile(r"-(20\d{6}|20\d{2}-\d{2}-\d{2})$")


def canon(base: str) -> str:
    """Spelling-only normalisation shared by every namespace: glued family/version and '.0' versions."""
    return _DOT_ZERO.sub(r"\1", _GLUED.sub(r"\1-\2", base))


def _load_manual() -> dict:
    doc = json.loads((Path(__file__).with_name("aliases.json")).read_text())
    doc["*"] = {canon(k): {**v, "model_id": canon(v["model_id"])} for k, v in doc.get("*", {}).items()}
    return doc


MANUAL = _load_manual()


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


_UNRESTRICTED = re.compile(r"-(uncensored|unrestricted|abliterated|heretic|nsfw|venice-edition)\b")


def policy(model_id: str) -> tuple[str, str | None]:
    """('unrestricted', base model) for uncensored / abliterated fine-tunes, else ('standard', None).
    glm-5-3-flash-uncensored -> ('unrestricted', 'glm-5-3-flash')."""
    m = _UNRESTRICTED.search(model_id)
    if not m:
        return "standard", None
    return "unrestricted", (model_id[: m.start()] + model_id[m.end():]).strip("-") or None


def normalize(namespace: str, key: str, name: str | None = None) -> tuple[str, str]:
    """Return (model_id, variant) for an external key of a namespace (aa | da | mm | arena | openrouter | kie | codex)."""
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
    elif namespace == "arena":
        # Arena display names: 'claude-opus-5.5-max', 'dreamina-seedance-2.5-720p', 'veo-3.1-audio-1080p',
        # 'gpt-image-2 (medium)', 'flux-3-video-20260811'.
        base, variant = _variant_from_paren(key)
        base = _DATE_SUFFIX.sub("", slugify(base))
        parts = []
        m = _RES_SUFFIX.search(base)
        if m:
            base, parts = base[: m.start()], [m.group(1)]
        if base.endswith("-audio"):
            base, parts = base[: -len("-audio")], ["audio"] + parts
        m = _TIER_SUFFIX.search(base)
        if m:
            base, parts = base[: m.start()], [m.group(1)] + parts
        variant = "-".join(parts) or variant
    else:
        base = key.split(":")[0]
        if namespace == "bridgebench" and base.startswith("openrouter/"):
            base = base[len("openrouter/"):]
        if namespace in ("openrouter", "hermes_providers", "bridgebench") and "/" in base:
            base = base.split("/", 1)[1].split("/")[0]  # vendor/model[/service-tier, e.g. /flex]
        if namespace == "kie" and "/" in base:
            base = base.rsplit("/", 1)[1]
        base = slugify(base)
    if namespace in ("kie", "mm", "arena"):
        for prefix in VENDOR_PREFIXES:
            if base.startswith(prefix):
                base = base[len(prefix):]
    if namespace in ("mm", "da") and not variant:
        m = _RES_SUFFIX.search(base)
        if m:
            base, variant = base[: m.start()], m.group(1)
    base = canon(base)
    alias = MANUAL.get("*", {}).get(base)
    if alias:
        base = alias["model_id"]
    return base, variant

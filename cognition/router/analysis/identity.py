"""Deterministic model identities: every external key is normalised to (model_id, variant).

No fuzzy matching: two sources refer to the same model only when their normalised keys are equal or a
manual alias (aliases.json, each entry justified) says so. Unmatched keys simply stay their own model.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from walter_router import instance

TIERS = ("non-reasoning", "minimal", "low", "medium", "high", "xhigh", "max")
VENDOR_PREFIXES = ("google-", "openai-", "anthropic-", "meta-", "microsoft-", "alibaba-", "bytedance-",
                   "black-forest-labs-")
BENCHMARK_NAMESPACES = ("aa", "aa_eval", "aa_decision", "da", "mm", "arena", "bridgebench", "aa_stt", "agentset", "mteb")
_TIER_SUFFIX = re.compile(r"-(" + "|".join(TIERS) + r")$")
_PAREN = re.compile(r"\(([^)]*)\)")
_GLUED = re.compile(r"(?<![a-z0-9])([a-z]{3,})(\d)")      # wan2-7 -> wan-2-7, flux1-1 -> flux-1-1 (not h3, v2, o1)
_DOT_ZERO = re.compile(r"(-\d+)-0(?=-[a-z]|$)")           # seedance-2-0-fast -> seedance-2-fast (not qwen-3-0-6b)
_RES_SUFFIX = re.compile(r"-(\d{3,4}p|\d(?:-\d)?k)$")    # leaderboard rows per output resolution
_DATE_SUFFIX = re.compile(r"-(20\d{6}|20\d{2}-\d{2}-\d{2})$")


def canon(base: str) -> str:
    """Spelling-only normalisation shared by every namespace: glued family/version and '.0' versions."""
    return _DOT_ZERO.sub(r"\1", _GLUED.sub(r"\1-\2", base))


AUTO_ALIASES = instance.config_path("aliases_auto.json")   # the instance's learned links, else the shipped ones


def _load_manual() -> dict:
    """aliases.json (hand-written) + config/aliases_auto.json (validated additions by the analysis agent)."""
    doc = json.loads((Path(__file__).with_name("aliases.json")).read_text())
    star = dict(doc.get("*", {}))
    if AUTO_ALIASES.exists():
        for k, v in json.loads(AUTO_ALIASES.read_text()).get("aliases", {}).items():
            star.setdefault(k, v)  # a hand-written alias always wins
    doc["*"] = {canon(k): {**v, "model_id": canon(v["model_id"])} for k, v in star.items()}
    return doc


def reload() -> None:
    global MANUAL
    MANUAL = _load_manual()


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


_WHISPER_SHORT = re.compile(r"\(L, (v\d)(, Turbo)?\)")       # AA: 'Whisper (L, v3, Turbo)' = Whisper Large v3 Turbo
_AGENTSET_VENDORS = ("cohere-", "voyage-ai-", "baai-", "openai-")   # 'Cohere Rerank 4 Pro' -> rerank-4-pro (API id)


def _compact(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def stt_name(model: str, host: str | None = None) -> str:
    """AA Speech-to-Text row name without its host: 'Whisper (L, v3, Turbo), Groq' -> 'Whisper Large v3 Turbo',
    'Parakeet TDT 0.6B V3, Togetherai' -> 'Parakeet TDT 0.6B V3' (the host is AA's Provider column)."""
    name = _WHISPER_SHORT.sub(lambda m: f"Large {m.group(1)}" + (" Turbo" if m.group(2) else ""), model).strip()
    head, sep, tail = name.rpartition(", ")
    h, t = _compact(host), _compact(tail)
    if sep and h and t and (t in h or h in t):
        name = head
    return name


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
    if namespace == "aa_decision":
        # 'typesafe_jev-1-13', 'anthropic_claude-haiku-5-5-low' (host_model; LLM rows carry their effort like AA)
        key = key.split("_", 1)[1] if "_" in key else key
        _, variant = _variant_from_paren((name or "").split(",")[0] + (")" if "," in (name or "") else ""))
        base = _TIER_SUFFIX.sub("", key)
    elif namespace == "aa":
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
    elif namespace == "aa_stt":
        # 'Gemini 3.1 Flash-Lite Preview (Minimal)' -> gemini-3-1-flash-lite-preview / minimal; name = the host
        base, variant = _variant_from_paren(stt_name(key, name))
        base = slugify(base)
    elif namespace == "agentset":
        base = slugify(key)
        for prefix in _AGENTSET_VENDORS:
            if base.startswith(prefix):
                base = base[len(prefix):]
    elif namespace == "mteb":
        base = slugify(key.split("__", 1)[-1])   # results folder 'Qwen__Qwen3-Embedding-8B' (org__model)
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

"""Research by category (owner, 2026-10-22: « que le sous-module de recherche soit divisé par catégorie pour pouvoir en
lancer une indépendamment des autres »). Each category says which sources it reads and, for sources shared by
several categories (Arena, AA media, Design Arena), which parts: a category run reads only its parts and merges them
into the last complete snapshot, so the other categories' data stays as it was.

    walter-router research text | image | video | audio | memory | decision | prices | hosts | plans | all
"""
from __future__ import annotations

import importlib

NAMES = ("text", "image", "video", "audio", "memory", "decision", "prices", "hosts", "plans")


def get(name: str):
    if name not in NAMES:
        raise KeyError(f"unknown research category {name!r} (known: {', '.join(NAMES)})")
    return importlib.import_module(f"{__name__}.{name}")


def plan(names: list[str]) -> tuple[dict[str, set | None], bool]:
    """Sources to read for these categories (parts united; None = whole source) and whether plans are refreshed."""
    out: dict[str, set | None] = {}
    plans = False
    for n in names:
        cat = get(n)
        plans = plans or getattr(cat, "EXTRA", None) == "subscriptions"
        for kind, parts in cat.SOURCES.items():
            if kind in out and (out[kind] is None or parts is None):
                out[kind] = None
            else:
                out[kind] = (out.get(kind) or set()) | set(parts) if parts is not None else None
    return out, plans

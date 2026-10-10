"""Trigger cards (poste indexer): for each skill, how Monsieur would actually ask for it.

Derived from the skill content only (never from user messages — that is the learning loop's job), keyed by the
content hash, regenerated when the skill changes, stored in the registry (skills.cards).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import postes, registry, store

VERSION = "card-v1"
BODY_CHARS = 14000
FIELDS = ("summary", "kind", "intents_fr", "intents_en", "entities", "symptoms", "not_for")
PROMPT = """You index one procedural skill of W.Alter, the personal AI agent of Monsieur (French; he writes informal
French, often without accents, sometimes mixing English; he refers to his own services and projects by name).
Read the skill and write the card that lets a retriever recognise, from one user message plus the previous turn,
that this skill is the one to load.

Return JSON only:
{
 "summary": "<= 140 chars, starts with 'Use when' / 'Use for': the trigger class, concrete",
 "kind": "procedure | workflow | reference | persona | integration",
 "intents_fr": ["12 realistic messages Monsieur would send that need this skill, varied: requests, complaints, follow-ups, short and long, with his vocabulary"],
 "intents_en": ["5 short English formulations"],
 "entities": ["services, tools, APIs, providers, projects, hosts, ports, file paths, commands the skill is about (max 25)"],
 "symptoms": ["error messages or observable symptoms that should lead here (max 10, [] if none)"],
 "not_for": ["max 4 nearby tasks this skill does NOT cover"]
}
"""


def _files(s: store.Skill) -> str:
    files = [str(p.relative_to(s.path)) for p in sorted(s.path.rglob("*"))
             if p.is_file() and p.name not in ("SKILL.md", store.SIDECAR) and "__pycache__" not in p.parts]
    return ("\n\nFiles: " + ", ".join(files[:40])) if files else ""


def generate(s: store.Skill) -> tuple[dict | None, str | None]:
    prompt = (PROMPT + f"\nSkill name: {s.name}\nDomain: {s.domain or '-'}\nDescription: {s.description}\n\n"
              f"SKILL.md (+ file list):\n{s.body[:BODY_CHARS]}{_files(s)}")
    card, route = postes.ask_json("indexer", prompt, require="summary", timeout=300)
    if not card:
        return None, None
    return {k: card.get(k, "" if k in ("summary", "kind") else []) for k in FIELDS}, route


def refresh(skills: list[store.Skill] | None = None, workers: int = 8) -> dict:
    """(Re)generate the cards of new or changed skills; returns counts."""
    skills = skills if skills is not None else list(store.iter_skills(include_archived=True))
    have = registry.cards()
    todo = [s for s in skills if have.get(s.name, {}).get("sha") != store.tree_hash(s.path)]

    def one(s):
        card, route = generate(s)
        if card:
            registry.put_card(s.name, store.tree_hash(s.path), card, route, VERSION)
        return bool(card)

    with ThreadPoolExecutor(workers) as ex:
        ok = sum(ex.map(one, todo))
    return {"todo": len(todo), "ok": ok, "failed": len(todo) - ok}

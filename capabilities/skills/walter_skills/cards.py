"""Trigger cards (poste skills.indexer): for each skill, how a user would actually ask for it.

A card is derived from the skill content only (never from user queries — that is the learner's job), keyed by the
skill's content hash, so it is regenerated when the skill changes. Stored in index/cards/<name>.json (git-tracked,
small). Skill text is secret-masked before it leaves the VM; calls go through walter_memory.llm (budget + ledger).
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import store

sys.path.insert(0, "/opt/walter-memory")
from walter_memory import llm  # noqa: E402
from walter_memory.logs import mask  # noqa: E402

CARDS = store.ROOT / "index" / "cards"
MODEL = "openai/gpt-6-luna"  # provisional holder of poste skills.indexer (Walter Router), see PLAN P10.2
VERSION = "card-v1"
BODY_CHARS = 14000

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

Skill name: {name}
Domain: {domain}
Description: {description}

SKILL.md (+ file list):
{body}"""


def card_path(name: str) -> Path:
    return CARDS / f"{name}.json"


def load(name: str) -> dict | None:
    p = card_path(name)
    return json.loads(p.read_text()) if p.exists() else None


def _files(s: store.Skill) -> str:
    files = [str(p.relative_to(s.path)) for p in sorted(s.path.rglob("*")) if p.is_file()
             and p.name not in ("SKILL.md", store.SIDECAR)]
    return ("\n\nFiles: " + ", ".join(files[:40])) if files else ""


def generate(s: store.Skill, model: str = MODEL) -> dict:
    sha = store.tree_hash(s.path)
    body = mask(s.body[:BODY_CHARS]) + _files(s)
    prompt = (PROMPT.replace("{name}", s.name).replace("{domain}", s.domain or "-")
              .replace("{description}", mask(s.description)).replace("{body}", body))
    r = llm.chat([{"role": "user", "content": prompt}], model=model, processor="skills.indexer",
                 processor_version=VERSION, privacy_class="cloud_allowed", budget="backfill",
                 purpose=f"card {s.name}", timeout=180, reasoning={"effort": "low"})
    m = re.search(r"\{.*\}", r["content"], re.S)
    card = json.loads(m.group(0))
    card = {k: card.get(k, [] if k != "summary" and k != "kind" else "") for k in
            ("summary", "kind", "intents_fr", "intents_en", "entities", "symptoms", "not_for")}
    return {"name": s.name, "sha": sha, "model": model, "version": VERSION, "cost_usd": r.get("cost_usd"), **card}


def build(skills: list[store.Skill], workers: int = 8, force: bool = False) -> dict:
    CARDS.mkdir(parents=True, exist_ok=True)
    todo = []
    for s in skills:
        c = load(s.name)
        if force or not c or c.get("sha") != store.tree_hash(s.path) or c.get("version") != VERSION:
            todo.append(s)
    stats = {"todo": len(todo), "ok": 0, "error": 0, "cost_usd": 0.0}

    def one(s):
        try:
            return s, generate(s), None
        except Exception as e:  # noqa: BLE001
            return s, None, str(e)[:200]

    with ThreadPoolExecutor(workers) as ex:
        for s, card, err in ex.map(one, todo):
            if card:
                card_path(s.name).write_text(json.dumps(card, ensure_ascii=False, indent=1) + "\n")
                stats["ok"] += 1
                stats["cost_usd"] += card.get("cost_usd") or 0
            else:
                stats["error"] += 1
                print("card error", s.name, err, file=sys.stderr)
    return stats

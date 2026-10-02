"""Context engine (P6, §31 get_context, A8): assemble the memory payload for a model call, by budgeted sections.

Sections (in this order, stable first so provider prompt caches keep hitting):
  1. profile     — compiled profile (USER.md), stable across turns
  2. people      — short Kardex card for people actually named in the query (L0 name match)
  3. knowledge   — derived knowledge relevant to the query (search lane 'derived')
  4. evidence    — original events (messages, e-mails, calendar…) when the query asks when/who/what was said
Each section has a token budget; the trace (sources, sizes, timings) is returned for measurement.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from . import search, social
from .db import connection

USER_MD = Path("/root/.hermes/memories/USER.md")
DEFAULT_BUDGET = {"profile": 600, "people": 400, "knowledge": 900, "evidence": 500}
EVIDENCE_HINT = re.compile(r"(?i)\b(quand|when|qui a dit|who said|m'a dit|told me|a écrit|wrote|message|mail|e-?mail|"
                           r"conversation|discut|parl[ée]|dernière fois|last time|hier|yesterday|semaine dernière|last week|"
                           r"rendez-vous|meeting|agenda|calendar|photo|vocal|voice note)\b")
_names_cache: tuple[float, list[tuple[str, str]]] | None = None


def tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _clip(lines: list[str], budget: int) -> tuple[str, int]:
    out, used = [], 0
    for line in lines:
        t = tokens(line)
        if used + t > budget:
            break
        out.append(line); used += t
    return "\n".join(out), used


def _known_people() -> list[tuple[str, str]]:
    """(lowercase name, entity_id) for people Monsieur actually talks with — refreshed every 10 minutes."""
    global _names_cache
    if _names_cache and time.time() - _names_cache[0] < 600:
        return _names_cache[1]
    with connection() as conn:
        rows = conn.execute("""select distinct on (lower(n)) lower(n) n, e.entity_id::text
                               from core.entities e join kardex.relationship_baselines b
                                 on b.entity_id = e.entity_id and b.window_name = 'all' and b.messages >= 20
                               cross join lateral unnest(array[e.canonical_name] || e.aliases) n
                               where e.entity_type = 'person' and length(n) >= 3 and n !~ '^[@+]'
                               order by lower(n), b.messages desc""").fetchall()
    _names_cache = (time.time(), [(r["n"], r["entity_id"]) for r in rows])
    return _names_cache[1]


def people_in(query: str) -> list[str]:
    q = f" {query.lower()} "
    return list(dict.fromkeys(eid for name, eid in _known_people()
                              if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", q)))[:2]


def _card_lines(entity_id: str) -> list[str]:
    c = social.person_card(entity_id, "cloud_allowed")
    e, rel = c["entity"], c["relationship"].get("all") or {}
    acc = sorted({f"{a['account']}" for a in c["accounts"]})
    lines = [f"- {e['canonical_name']} ({', '.join(acc)}): {rel.get('messages', 0)} messages, "
             f"dernier contact {str(rel.get('last_contact') or '?')[:10]}, "
             f"Monsieur initie {round(100 * (rel.get('initiation_ratio_me') or 0))} % des échanges"]
    k = c["kardex"].get("contact") or {}
    if k:
        lines.append("  " + ", ".join(f"{x}: {k[x]}" for x in ("relationship_type", "occupation", "location_current") if k.get(x)))
    lines += [f"  • {cl['claim']}" for cl in (c["kardex"].get("claims") or [])[:5]
              if cl["mention_policy"] in ("free", "contextual_only")]
    lines += list(dict.fromkeys(f"  ⚠ {d['observation']}" for d in c["deviations"]))[:2]
    return lines


def _dedupe(lines: list[str], threshold: float = 0.88) -> list[str]:
    """Drop near-duplicates (legacy memories repeat the same fact with small variations)."""
    if len(lines) < 2:
        return lines
    v = search.embed([re.sub(r"\s*\|.*$", "", l)[:400] for l in lines])
    keep = []
    for i in range(len(lines)):
        if all(float(v[i] @ v[j]) < threshold for j in keep):
            keep.append(i)
    return [lines[i] for i in keep]


def get_context(query: str, *, budget: dict | None = None, max_privacy: str = "cloud_allowed",
                include_profile: bool = True) -> dict:
    """Returns {"text": assembled block, "sections": {...}, "trace": {...}}."""
    b = {**DEFAULT_BUDGET, **(budget or {})}
    t0 = time.perf_counter()
    sections, trace = {}, {"query_chars": len(query), "sections": {}}
    if include_profile and b["profile"] > 0 and USER_MD.exists():
        text, used = _clip(USER_MD.read_text().splitlines(), b["profile"])
        sections["profile"] = text
        trace["sections"]["profile"] = {"tokens": used}
    named = people_in(query) if b["people"] > 0 or b["evidence"] > 0 else []
    if b["people"] > 0:
        t = time.perf_counter()
        lines = [l for eid in named for l in _card_lines(eid)]
        text, used = _clip(lines, b["people"])
        if text:
            sections["people"] = text
        trace["sections"]["people"] = {"tokens": used, "ms": round((time.perf_counter() - t) * 1000)}
    if b["knowledge"] > 0:
        t = time.perf_counter()
        res = search.search(query, limit=12, sources=["hindsight", "user_model_compiler", "walter"],
                            max_privacy=max_privacy, rerank=True)
        lines = [f"- {r['text'].strip()} ({str(r['occurred_at'] or '')[:10]})" for r in res]
        text, used = _clip(_dedupe(list(dict.fromkeys(lines))), b["knowledge"])
        if text:
            sections["knowledge"] = text
        trace["sections"]["knowledge"] = {"tokens": used, "candidates": len(res), "ms": round((time.perf_counter() - t) * 1000),
                                          "refs": [r["ref_id"] for r in res[:8]]}
    if b["evidence"] > 0 and EVIDENCE_HINT.search(query):
        t = time.perf_counter()
        res = search.search(query, limit=8, include_derived=False, max_privacy=max_privacy, rerank=True)
        direct = []
        for eid in named:   # "what did X tell me": X's own latest messages first
            card = social.person_card(eid, max_privacy)
            direct += [f"- [{str(m['occurred_at'])[:16]} · {m['source_account']} · {card['entity']['canonical_name']}] "
                       f"{(m['content'] or '')[:300].strip()}" for m in card["recent_interactions"][:6] if m["content"]]
        lines = direct + [f"- [{str(r['occurred_at'])[:16]} · {r['source']}/{r['label']}{' · ' + r['actor'] if r.get('actor') else ''}] "
                 f"{r['text'][:300].strip()}" for r in res]
        text, used = _clip(lines, b["evidence"])
        if text:
            sections["evidence"] = text
        trace["sections"]["evidence"] = {"tokens": used, "ms": round((time.perf_counter() - t) * 1000),
                                         "refs": [r["ref_id"] for r in res[:8]]}
    titles = {"profile": "Profil de Monsieur", "people": "Personnes concernées (Kardex)",
              "knowledge": "Mémoire pertinente", "evidence": "Sources d'origine"}
    block = "\n\n".join(f"## {titles[k]}\n{v}" for k, v in sections.items())
    trace["total_tokens"] = tokens(block) if block else 0
    trace["latency_ms"] = round((time.perf_counter() - t0) * 1000)
    return {"text": block, "sections": sections, "trace": trace}

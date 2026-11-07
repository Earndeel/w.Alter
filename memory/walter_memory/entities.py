"""Entities beyond people and V1 relations (Memory V1 P1.3): projects, places, organisations — resolved without a model.

Anchors live in core.entities (people already there, from identities); this module adds the other kinds and links
V1 knowledge to them:
  seeds      the projects the instance actually has: Walter's modules (`walter modules`) and /projects/<client>/<name>
             (+ the umbrella W.Alter), each with its aliases; a place is created by flows (GPS, local_only)
  resolve    a mention ("project:Walter Memory V1", "person:Hani") → an entity, in this order: exact alias (accents,
             case, punctuation ignored) → alias contained as whole words → a person with that exact unique name. A
             phase label ("P1.1") belongs to the project it is spoken of with. Anything else stays an unconfirmed
             candidate (attributes.confirmed = false), never merged into an existing entity.
  link       core.derived_items.subject_entity_ids + V1 relations in core.relationships (owner works_on project,
             dated by the knowledge's evidence, privacy = the knowledge's class), idempotent.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import unicodedata
from functools import lru_cache
from pathlib import Path

from .db import connection

log = logging.getLogger("walter.entities")
BUILDER = "entities@1"
PHASE = re.compile(r"^(p|lot|phase|step|étape|etape)\s*\d+(\.\d+)*$", re.I)
SYNONYMS = {   # what the owner and the agents call a module, beyond its id (2026-11-03, from V1 knowledge)
    "memory": ["walter memory", "memory", "organic memory", "memory v1", "walter memory v1", "mémoire organique",
               "memoire organique", "kardex", "walter-memory"],
    "context": ["walter context", "walter-context", "context"],
    "router": ["walter router", "walter-router", "walter-llm", "router"],
    "skills": ["walter skills", "walter-skills"],
    "soul": ["walter soul", "walter-soul"],
    "browse": ["walter browse", "walter-browse"],
    "secrets": ["walter secrets", "walter-secrets"],
    "ops": ["walter ops", "walter-ops", "walter backup"],
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9.]+", " ", s).strip()


def owner_id(conn) -> str | None:
    r = conn.execute("""select l.entity_id::text from core.identity_links l join core.source_identities s
                        on s.identity_id = l.identity_id where s.is_self limit 1""").fetchone()
    return r["entity_id"] if r else None


def _modules() -> list[dict]:
    try:
        out = json.loads(subprocess.run(["walter", "modules"], capture_output=True, text=True, timeout=30).stdout)
        return [{"id": m["id"], "root": m.get("root")} for m in out.get("modules", [])]
    except Exception as e:  # the registry is the source; without it only /projects seeds
        log.warning("walter modules unavailable: %s", e)
        return []


def seeds() -> list[dict]:
    out = [{"name": "W.Alter", "aliases": ["walter", "w.alter", "w alter"], "attributes": {"kind": "umbrella"}}]
    for m in _modules():
        mid = m["id"]
        out.append({"name": f"Walter {mid.capitalize()}", "aliases": [mid, f"walter {mid}", f"walter-{mid}",
                                                                   *SYNONYMS.get(mid, [])],
                    "attributes": {"kind": "walter_module", "module": mid, "root": m.get("root")}})
    for d in sorted(Path("/projects").glob("*/*")):
        if d.is_dir() and not d.name.endswith(".bundle"):
            out.append({"name": d.name, "aliases": [d.name, d.name.replace("-", " ")],
                        "attributes": {"kind": "project", "client": d.parent.name, "path": str(d)}})
    return out


def ensure(conn, entity_type: str, name: str, *, aliases=(), attributes: dict | None = None,
           privacy_class: str | None = None) -> str:
    """The entity of that type whose name or alias matches (normalized), else a new one. Aliases are added, never
    removed; attributes merged."""
    keys = {norm(name), *(norm(a) for a in aliases)} - {""}
    row = conn.execute("""select entity_id::text, aliases from core.entities where entity_type = %s and status = 'active'
                          and (lower(canonical_name) = any(%s) or exists (select 1 from unnest(aliases) a
                                                                           where lower(a) = any(%s)))
                          order by created_at limit 1""", (entity_type, list(keys), list(keys))).fetchone()
    if row:
        new = sorted(keys - {a.lower() for a in row["aliases"] or []})
        conn.execute("""update core.entities set aliases = array(select distinct unnest(aliases || %s::text[])),
                          attributes = attributes || %s, updated_at = now() where entity_id = %s""",
                     (new, json.dumps(attributes or {}), row["entity_id"]))
        return row["entity_id"]
    return conn.execute("""insert into core.entities (entity_type, canonical_name, aliases, attributes, privacy_class)
                           values (%s, %s, %s, %s, %s) returning entity_id::text""",
                        (entity_type, name, sorted(keys), json.dumps(attributes or {}), privacy_class)).fetchone()["entity_id"]


def seed() -> dict:
    with connection() as conn:
        ids = [ensure(conn, "project", s["name"], aliases=s["aliases"], attributes={**s["attributes"], "confirmed": True})
               for s in seeds()]
    _aliases.cache_clear()
    return {"projects": len(ids)}


@lru_cache(maxsize=1)
def _aliases() -> list[tuple[str, str, str]]:
    """(normalized alias, entity_id, type) of projects/organisations, longest first (for containment)."""
    with connection() as conn:
        rows = conn.execute("""select entity_id::text, entity_type, canonical_name, aliases from core.entities
                               where entity_type in ('project', 'organization') and status = 'active'""").fetchall()
    out = []
    for r in rows:
        for a in {r["canonical_name"], *(r["aliases"] or [])}:
            if norm(a):
                out.append((norm(a), r["entity_id"], r["entity_type"]))
    return sorted(out, key=lambda x: -len(x[0]))


def resolve_project(name: str) -> str | None:
    n = norm(name)
    if not n or PHASE.match(n):
        return None
    al = _aliases()
    for a, eid, _ in al:
        if a == n:
            return eid
    for a, eid, _ in al:          # "walter memory v1" → walter memory; whole words only, aliases of 4+ chars
        if len(a) >= 4 and re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", n):
            return eid
    return None


# Project names that are also everyday words: alone they say nothing about the owner's memory.
COMMON_ALIASES = {"llm", "ops", "bus", "lab", "logs", "soul", "core", "arena", "memory", "backup", "browse", "skills",
                  "secrets", "context", "runtime", "computer", "guardian", "paysages"}
ANCHOR_TTL_S = 600
_ANCHOR_AT = [0.0]


def anchors(text: str) -> list[dict]:
    """The owner's projects and organisations a message names (whole words, distinctive aliases of 3+ chars), one
    per entity. Deterministic and local, no model: walter-context uses it so a named project always reaches the
    owner's memory, whatever a decision model guessed (« Le site EDGEWISE, c'est où ? » planned as a web question,
    07/11). Names only, never content."""
    import time
    if time.time() - _ANCHOR_AT[0] > ANCHOR_TTL_S:     # long-lived callers see new projects within minutes
        _aliases.cache_clear()
        _ANCHOR_AT[0] = time.time()
    n = f" {norm(text)} "
    out, seen = [], set()
    for a, eid, etype in _aliases():
        if eid in seen or len(a) < 3 or a in COMMON_ALIASES:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", n):
            seen.add(eid)
            out.append({"alias": a, "entity_id": eid, "type": etype})
    return out


def resolve_person(conn, name: str) -> str | None:
    n = (name or "").strip().lower()
    if len(n) < 3:
        return None
    rows = conn.execute("""select entity_id::text from core.entities where entity_type = 'person' and status = 'active'
                           and (lower(canonical_name) = %s or %s = any(select lower(a) from unnest(aliases) a))
                           limit 2""", (n, n)).fetchall()
    return rows[0]["entity_id"] if len(rows) == 1 else None      # ambiguous: no link (a wrong merge is worse)


def mentions_of(item: dict) -> list[tuple[str, str]]:
    """(type, name) mentioned by a V1 knowledge item: its subject and the projects of its segment."""
    attrs = item.get("attributes") or {}
    out = []
    subj = attrs.get("subject") or ""
    if ":" in subj:
        kind, _, name = subj.partition(":")
        out.append((kind.strip(), name.strip()))
    out += [("project", p) for p in attrs.get("projects") or [] if isinstance(p, str)]
    return out


def link_items(item_ids: list[str] | None = None, *, limit: int = 5000) -> dict:
    """Resolve the mentions of V1 knowledge (extract2) and record subject_entity_ids + owner works_on project."""
    stats = {"items": 0, "linked": 0, "relations": 0, "candidates": 0}
    with connection() as conn:
        me = owner_id(conn)
        rows = conn.execute("""select item_id::text, kind, attributes, privacy_class, source_event_ids, valid_from,
                                      created_at, subject_entity_ids
                               from core.derived_items where generation = 'g1' and derived_by = 'l3.extract'
                                 and kind <> 'summary' and status in ('derived', 'verified')
                                 and (%s::uuid[] is null or item_id = any(%s::uuid[]))
                               order by created_at desc limit %s""", (item_ids, item_ids, limit)).fetchall()
        for r in rows:
            stats["items"] += 1
            ents: list[str] = []
            for kind, name in mentions_of(r):
                eid = None
                if kind == "project":
                    eid = resolve_project(name)
                    if eid is None and name and not PHASE.match(norm(name)) and len(norm(name)) >= 3:
                        eid = ensure(conn, "project", name, attributes={"confirmed": False, "origin": BUILDER})
                        stats["candidates"] += 1
                        _aliases.cache_clear()
                elif kind == "person":
                    eid = resolve_person(conn, name)
                if eid and eid not in ents:
                    ents.append(eid)
            if not ents:
                continue
            if set(ents) - set(map(str, r["subject_entity_ids"] or [])):
                conn.execute("""update core.derived_items set subject_entity_ids = array(select distinct unnest(
                                  coalesce(subject_entity_ids, '{}') || %s::uuid[])) where item_id = %s""", (ents, r["item_id"]))
                stats["linked"] += 1
            if me:
                for eid in ents:
                    t = conn.execute("select entity_type from core.entities where entity_id = %s", (eid,)).fetchone()
                    if t and t["entity_type"] == "project":
                        stats["relations"] += relate(conn, me, "works_on", eid, r["source_event_ids"],
                                                     r["privacy_class"], r["valid_from"] or r["created_at"])
    return stats


def relate(conn, subject_id: str, predicate: str, object_id: str, event_ids, privacy_class: str, at, *,
           derived_by: str = BUILDER, attributes: dict | None = None) -> int:
    """One V1 relation per (subject, predicate, object, builder): evidence accumulates, the window widens, the class
    can only tighten."""
    from . import privacy
    row = conn.execute("""select relationship_id, privacy_class, valid_from, attributes from core.relationships
                          where subject_id = %s and predicate = %s and object_id = %s and derived_by = %s
                            and generation = 'g1'""", (subject_id, predicate, object_id, derived_by)).fetchone()
    ids = [str(e) for e in event_ids or []]
    if row:
        seen = (row["attributes"] or {}).get("last_at")
        last = max(at, _ts(seen)) if seen else at
        conn.execute("""update core.relationships set source_event_ids = array(select distinct unnest(source_event_ids
                          || %s::uuid[])), valid_from = least(valid_from, %s), privacy_class = %s,
                          attributes = attributes || %s where relationship_id = %s""",
                     (ids, at, privacy.strictest(row["privacy_class"], privacy_class),
                      json.dumps({**(attributes or {}), "last_at": last.isoformat()}), row["relationship_id"]))
        return 0
    conn.execute("""insert into core.relationships (subject_id, predicate, object_id, valid_from, confidence, status,
                        derived_by, processor_version, source_event_ids, privacy_class, attributes, generation)
                    values (%s, %s, %s, %s, 1.0, 'derived', %s, '1', %s::uuid[], %s, %s, 'g1')""",
                 (subject_id, predicate, object_id, at, derived_by, ids, privacy_class,
                  json.dumps({**(attributes or {}), "last_at": at.isoformat()})))
    return 1


def _ts(s):
    from datetime import datetime
    return datetime.fromisoformat(s) if isinstance(s, str) else s


def card(entity_id: str, *, max_privacy: str = "cloud_allowed", limit: int = 12) -> dict:
    """A project's (or any entity's) current V1 knowledge and relations, for views and Context."""
    from . import privacy
    allowed = privacy.allowed_classes(max_privacy)
    with connection() as conn:
        e = conn.execute("""select entity_id::text, entity_type, canonical_name, aliases, attributes, privacy_class
                            from core.entities where entity_id = %s""", (entity_id,)).fetchone()
        items = conn.execute("""select item_id::text, kind, stage, scope, content, coalesce(valid_from, created_at) at
                                from core.derived_items where %s = any(subject_entity_ids) and generation = 'g1'
                                  and status in ('derived','verified') and (valid_to is null or valid_to > now())
                                  and privacy_class = any(%s) order by created_at desc limit %s""",
                             (entity_id, allowed, limit)).fetchall()
        rels = conn.execute("""select r.predicate, s.canonical_name subj, r.valid_from, r.attributes->>'last_at' last_at
                               from core.relationships r join core.entities s on s.entity_id = r.subject_id
                               where r.object_id = %s and r.generation = 'g1' and r.privacy_class = any(%s)""",
                            (entity_id, allowed)).fetchall()
    return {"entity": e, "knowledge": items, "relations": rels}

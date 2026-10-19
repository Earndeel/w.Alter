"""Canonical read boundary shared by search, memory ports and projections.

Checked per returned row against the canonical owner (never the index): current privacy class, every provenance
event/object, retractions, purges/quarantine and fragment freshness. Batched: one query per owner table per call, and
events are looked up with their occurred_at (from core.event_keys) so Postgres prunes core.events' partitions —
an event_id lookup alone plans against every partition (15-90 ms each, 2026-10-19).

Derived knowledge is readable when status is derived/verified, or legacy_derived (A2: Hindsight / user_model history,
read as legacy knowledge, never promoted) — always with non-empty provenance that is itself readable.
"""
from __future__ import annotations

import time

from . import privacy
from .db import connection

READABLE_DERIVED = ("derived", "verified", "legacy_derived")
_retracted: tuple[float, frozenset[str]] = (0.0, frozenset())


def retracted_ids(conn) -> frozenset[str]:
    """Targets of event.retracted, cached 60 s (retractions are rare; the indexer also hides their chunks)."""
    global _retracted
    if time.monotonic() - _retracted[0] > 60:
        rows = conn.execute("""select payload->>'target_event_id' as t from core.events
                               where event_type = 'event.retracted'""").fetchall()
        _retracted = (time.monotonic(), frozenset(r["t"] for r in rows if r["t"]))
    return _retracted[1]


def _events(conn, ids) -> dict[str, dict]:
    ids = list({str(i) for i in ids})
    if not ids:
        return {}
    keys = conn.execute("select event_id, occurred_at from core.event_keys where event_id = any(%s::uuid[])",
                        (ids,)).fetchall()
    if not keys:
        return {}
    rows = conn.execute("""select event_id::text as id, privacy_class, content from core.events
                           where occurred_at = any(%s) and event_id = any(%s)""",
                        ([k["occurred_at"] for k in keys], [k["event_id"] for k in keys])).fetchall()
    gone = retracted_ids(conn)
    return {r["id"]: {**r, "allowed": r["id"] not in gone} for r in rows}


def _objects(conn, ids) -> dict[str, dict]:
    ids = list({str(i) for i in ids})
    if not ids:
        return {}
    rows = conn.execute("""select id::text as id, privacy_class,
            coalesce(original_name,'') || E'\n' || coalesce(derived_text,'') as content,
            (purged_at is null and status not in ('quarantined','purged','deleted')) as allowed
            from core.objects where id = any(%s::uuid[])""", (ids,)).fetchall()
    return {r["id"]: r for r in rows}


def _readable(owner: dict | None) -> bool:
    return bool(owner) and owner["privacy_class"] == "cloud_allowed" and bool(owner.get("allowed"))


def canonical_filter(conn, rows: list[dict]) -> list[dict]:
    """The rows (order kept) whose canonical owner is currently cloud-readable and still contains the fragment."""
    rows = [r for r in rows if r.get("privacy_class") == "cloud_allowed"]
    by_kind: dict[str, set[str]] = {}
    for r in rows:
        by_kind.setdefault(r.get("kind"), set()).add(str(r.get("ref_id")))
    owners: dict[tuple[str, str], dict] = {}
    for i, v in _events(conn, by_kind.get("event", ())).items():
        owners[("event", i)] = v
    for i, v in _objects(conn, by_kind.get("object", ())).items():
        owners[("object", i)] = v
    if by_kind.get("derived"):
        items = conn.execute("""select item_id::text as id, privacy_class, content, status,
                                       coalesce(attributes->>'quarantined','false') in ('true','1') as quarantined,
                                       source_event_ids, source_object_ids
                                from core.derived_items where item_id = any(%s::uuid[])""",
                             (list(by_kind["derived"]),)).fetchall()
        src_e = _events(conn, {e for d in items for e in d["source_event_ids"]})
        src_o = _objects(conn, {o for d in items for o in d["source_object_ids"]})
        for d in items:
            provenance = [src_e.get(str(e)) for e in d["source_event_ids"]] + \
                         [src_o.get(str(o)) for o in d["source_object_ids"]]
            owners[("derived", d["id"])] = {
                "privacy_class": d["privacy_class"], "content": d["content"],
                "allowed": d["status"] in READABLE_DERIVED and not d["quarantined"] and bool(provenance)
                           and all(_readable(p) for p in provenance)}
    out = []
    for r in rows:
        owner = owners.get((r.get("kind"), str(r.get("ref_id"))))
        if not _readable(owner):
            continue
        # Mutable derived/object content can outlive an old search chunk. Never return that stale projection.
        fragment, canonical = (r.get("text") or "").strip(), (owner.get("content") or "").strip()
        if fragment and fragment in canonical:
            out.append(r)
    return out


def canonical_allowed(conn, row: dict) -> bool:
    """Check current canonical privacy, all provenance, retractions and index freshness."""
    return bool(canonical_filter(conn, [row]))


def filter_cloud_rows(conn, rows):
    return [row for row in canonical_filter(conn, rows)
            if not any(category == 'secret' for category, _ in privacy.detect(row.get('text') or ''))]


def query_privacy(query, caller='walter'):
    detections = privacy.detect(query)
    with connection() as conn:
        cls, _ = privacy.classify(conn, {'source': caller, 'source_account': 'walter-core',
                                       'event_type': 'note.recorded',
                                       'categories': {category for category, _ in detections}})
    return privacy.strictest(cls, 'local_only' if any(c == 'secret' for c, _ in detections) else 'cloud_allowed')

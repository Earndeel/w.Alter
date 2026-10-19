"""Canonical read boundary shared by search, memory ports and projections."""
from __future__ import annotations

from . import privacy
from .db import connection

def canonical_allowed(conn, row: dict) -> bool:
    """Check current canonical privacy, all provenance, retractions and index freshness."""
    if row.get('privacy_class') != 'cloud_allowed':
        return False
    kind, ref = row.get('kind'), row.get('ref_id')
    if kind == 'event':
        value = conn.execute("""select e.privacy_class, e.content,
            not exists (select 1 from core.events r where r.event_type='event.retracted'
              and r.payload @> jsonb_build_object('target_event_id',e.event_id::text)) as allowed
            from core.events e where e.event_id=%s limit 1""", (ref,)).fetchone()
    elif kind == 'object':
        value = conn.execute("""select privacy_class,
            coalesce(original_name,'') || E'\n' || coalesce(derived_text,'') as content,
            (purged_at is null and status not in ('quarantined','purged','deleted')) as allowed
            from core.objects where id=%s""", (ref,)).fetchone()
    elif kind == 'derived':
        value = conn.execute("""select d.privacy_class, d.content,
            (d.status in ('derived','verified')
             and coalesce(d.attributes->>'quarantined','false') not in ('true','1')
             and cardinality(d.source_event_ids)+cardinality(d.source_object_ids)>0
             and not exists (
               select 1 from unnest(d.source_event_ids) src(event_id) where not exists (
                 select 1 from core.events e where e.event_id=src.event_id and e.privacy_class='cloud_allowed'
                 and not exists (select 1 from core.events r where r.event_type='event.retracted'
                   and r.payload @> jsonb_build_object('target_event_id',e.event_id::text))))
             and not exists (
               select 1 from unnest(d.source_object_ids) src(id) where not exists (
                 select 1 from core.objects o where o.id=src.id and o.privacy_class='cloud_allowed'
                   and o.purged_at is null and o.status not in ('quarantined','purged','deleted')))) as allowed
            from core.derived_items d where d.item_id=%s""", (ref,)).fetchone()
    else:
        return False
    if not value or value['privacy_class'] != 'cloud_allowed' or not value.get('allowed'):
        return False
    # Mutable derived/object content can outlive an old search chunk. Never return that stale projection.
    fragment=(row.get('text') or '').strip()
    canonical=(value.get('content') or '').strip()
    return bool(fragment and fragment in canonical)


def filter_cloud_rows(conn, rows):
    return [row for row in rows if canonical_allowed(conn, row)
            and not any(category == 'secret' for category, _ in privacy.detect(row.get('text') or ''))]


def query_privacy(query, caller='walter'):
    detections = privacy.detect(query)
    with connection() as conn:
        cls, _ = privacy.classify(conn, {'source': caller, 'source_account': 'walter-core',
                                       'event_type': 'note.recorded',
                                       'categories': {category for category, _ in detections}})
    return privacy.strictest(cls, 'local_only' if any(c == 'secret' for c, _ in detections) else 'cloud_allowed')

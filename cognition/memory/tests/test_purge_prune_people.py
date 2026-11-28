"""Test database (27/11/2026): a purge also removes the group entity and the empty person entries that only the purged
messages justified; a person who still has a message elsewhere, or holds something of their own, is kept."""
import json
import uuid
from datetime import datetime, timedelta, timezone

from walter_memory import events, purge
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)


def msg(thread, sender, text):
    ev = {"event_type": "message.received", "source": "beeper", "source_account": "whatsapp",
          "source_id": uuid.uuid4().hex, "thread_id": thread, "content": text,
          "occurred_at": NOW - timedelta(hours=2), "privacy_class": "redacted_cloud",
          "actor": {"external_id": sender, "account": "whatsapp", "display_name": sender}}
    return events.record_events([ev])["event_ids"][0]


def entity_of(conn, sender):
    row = conn.execute("""select l.entity_id from core.source_identities s join core.identity_links l using (identity_id)
                          where s.source = 'beeper' and s.external_id = %s""", (sender,)).fetchone()
    return row and row["entity_id"]


def person(conn, sender, attributes=None):
    """The person entry the social resolver would create for that sender."""
    ident = conn.execute("select identity_id from core.source_identities where source='beeper' and external_id=%s",
                         (sender,)).fetchone()["identity_id"]
    ent = conn.execute("""insert into core.entities (entity_type, canonical_name, attributes) values ('person', %s, %s)
                          returning entity_id""", (sender, json.dumps(attributes or {}))).fetchone()["entity_id"]
    conn.execute("""insert into core.identity_links (identity_id, entity_id, status, confidence, method)
                    values (%s, %s, 'confirmed', 1, 'test')""", (ident, ent))
    return ent


def test_purge_removes_the_group_and_its_empty_people_only():
    tag = uuid.uuid4().hex[:8]
    group, other = f"!group-{tag}:test", f"!dm-{tag}:test"
    stranger, friend, known = f"@stranger-{tag}", f"@friend-{tag}", f"@known-{tag}"
    purged = [msg(group, stranger, "navette 7h"), msg(group, friend, "ok"), msg(group, known, "merci")]
    msg(other, friend, "on se voit demain ?")                      # the friend still writes to Monsieur elsewhere
    with connection() as conn:
        g = conn.execute("""insert into core.entities (entity_type, canonical_name, attributes)
                            values ('group', 'Navette', jsonb_build_object('thread_id', %s::text)) returning entity_id""",
                         (group,)).fetchone()["entity_id"]
        ents = {s: person(conn, s, {"note": "met in Lyon"} if s == known else None) for s in (stranger, friend, known)}
        for e in ents.values():
            conn.execute("""insert into core.relationships (subject_id, predicate, object_id, confidence, status, derived_by)
                            values (%s, 'member_of', %s, 0.9, 'derived', 'test')""", (e, g))

    out = purge.purge(reason="test", requested_by="pytest", event_ids=purged, execute=True)
    assert out["removed"]["group_entities"] == 1
    assert out["removed"]["person_entities"] == 1                   # the stranger only
    with connection() as conn:
        assert conn.execute("select 1 from core.entities where entity_id = %s", (g,)).fetchone() is None
        assert entity_of(conn, stranger) is None
        assert conn.execute("select 1 from core.source_identities where external_id = %s", (stranger,)).fetchone() is None
        assert entity_of(conn, friend) == ents[friend]              # still has a message
        assert entity_of(conn, known) == ents[known]                # holds something of their own

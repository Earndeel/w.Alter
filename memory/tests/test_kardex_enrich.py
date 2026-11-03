"""Kardex enrichment on the test database: claims about the CONTACT only, from the contact's own messages (quote
found), never the owner's private information; sensitivity tightened by type and mention policy derived; proposed."""
import json
import uuid
from datetime import datetime, timedelta, timezone

from walter_memory import events, kardex_enrich
from walter_memory.db import connection


def test_enrich_keeps_only_the_contacts_own_statements_and_restricts_sensitive_ones():
    tag = uuid.uuid4().hex[:6]
    with connection() as conn:
        ent = conn.execute("insert into core.entities (entity_type, canonical_name) values ('person', %s) returning entity_id::text",
                           (f"Nok {tag}",)).fetchone()["entity_id"]
        ident = conn.execute("""insert into core.source_identities (source, account, external_id, display_name)
                                values ('beeper', 'pytest', %s, %s) returning identity_id::text""",
                             (f"nok-{tag}", f"Nok {tag}")).fetchone()["identity_id"]
        conn.execute("insert into core.identity_links (identity_id, entity_id, method, status) values (%s, %s, 'pytest', 'confirmed')",
                     (ident, ent))
    thread, now = f"!t{tag}:beeper.local", datetime.now(timezone.utc)
    texts = [("c", "Je travaille comme infirmière à l'hôpital de Chiang Mai"), ("o", "Moi j'ai mon rendez-vous médical mardi"),
             ("c", "J'adore la randonnée le week-end"), ("c", "Mon médecin m'a dit que j'ai de l'asthme")]
    for k, (who, t) in enumerate(texts):
        events.record_events([{"event_type": "message.received" if who == "c" else "message.sent", "source": "beeper",
                               "source_account": "pytest", "source_id": uuid.uuid4().hex, "thread_id": thread,
                               "occurred_at": now - timedelta(hours=5 - k), "content": t, "privacy_class": "redacted_cloud",
                               "actor_identity_id": ident if who == "c" else None,
                               "payload": {"chat": {"type": "single", "network": "line"}}}])

    def chat(messages, **kw):
        assert f"Nok {tag}" not in messages[0]["content"]              # pseudonymised before leaving
        return {"model": "scripted", "content": json.dumps({"claims": [
            {"claim": "Contact est infirmière à Chiang Mai", "type": "work", "sensitivity": "normal", "msgs": [1],
             "quote": "infirmière à l'hôpital de Chiang Mai"},
            {"claim": "Monsieur a un rendez-vous médical mardi", "type": "health", "sensitivity": "sensitive", "msgs": [2],
             "quote": "mon rendez-vous médical mardi"},                  # the owner's own life: refused
            {"claim": "Contact aime la randonnée", "type": "interest", "sensitivity": "normal", "msgs": [3],
             "quote": "J'adore la randonnée"},
            {"claim": "Contact a de l'asthme", "type": "health", "sensitivity": "normal", "msgs": [4],
             "quote": "j'ai de l'asthme"}]})}
    r = kardex_enrich.enrich(ent, chat=chat)
    assert r["claims"] == 3 and r["rejected"] == 1
    with connection() as conn:
        rows = {x["claim"]: x for x in conn.execute("""select c.claim, c.status, c.sensitivity, c.mention_policy from kardex.claims c
                    join core.entities e on e.kardex_contact_id = c.contact_id where e.entity_id = %s""", (ent,))}
    assert "Monsieur a un rendez-vous médical mardi" not in rows
    assert rows["Contact a de l'asthme"]["sensitivity"] == "highly_sensitive"
    assert rows["Contact a de l'asthme"]["mention_policy"] == "never_reference"
    assert rows["Contact aime la randonnée"]["mention_policy"] == "free" and rows["Contact aime la randonnée"]["status"] == "proposed"

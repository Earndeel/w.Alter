"""Implicit references (E2E 20/11, owner: « Lier "il", "elle", "cette personne" ou "le" à une entité récente lorsque
le contexte l'identifie avec suffisamment de certitude. En cas d'ambiguïté, Walter demande confirmation. Ne crée pas
de relation artificielle uniquement parce qu'une personne a été mentionnée récemment. »). Throwaway DB; the recent
window is placed at a date of its own so other tests' messages never enter it."""
import uuid
from datetime import datetime, timedelta, timezone

from walter_memory import context, digest, events
from walter_memory.db import connection

def fresh():   # a window of its own per test (days apart): no other test's message is recent there
    return datetime(2031, 3, 1, 12, 0, tzinfo=timezone.utc) + timedelta(days=uuid.uuid4().int % 20000)


def contact(name=None):
    name = name or "Reftest " + "".join(chr(97 + int(c, 16) % 26) for c in uuid.uuid4().hex[:7]).capitalize()
    with connection() as conn:
        eid = conn.execute("""insert into core.entities (entity_type, canonical_name, aliases) values ('person', %s, %s)
                              returning entity_id::text""", (name, [name.lower()])).fetchone()["entity_id"]
        iid = events.upsert_identity(conn, "beeper", {"external_id": f"@{uuid.uuid4().hex[:8]}:pytest",
                                                       "account": "pytest", "display_name": name})
        conn.execute("""insert into core.identity_links (identity_id, entity_id, status, confidence, method)
                        values (%s, %s, 'confirmed', 1.0, 'pytest')""", (iid, eid))
    return {"name": name, "entity": eid, "identity": iid}


def wrote(c, at, chat_type="single", voice=False):
    events.record_events([{"event_type": "message.received", "source": "beeper", "source_account": "pytest",
                           "source_id": uuid.uuid4().hex, "thread_id": f"!ref-{uuid.uuid4().hex[:8]}:pytest",
                           "occurred_at": at, "content": None if voice else "Salut !", "privacy_class": "cloud_allowed",
                           "actor_identity_id": c["identity"],
                           "payload": {"chat": {"type": chat_type, "title": c["name"]}}}])


def counts():
    with connection() as conn:
        return tuple(conn.execute(f"select count(*) n from {t}").fetchone()["n"]
                     for t in ("core.identity_links", "core.relationships", "core.derived_items"))


def test_the_only_contact_who_just_wrote_is_the_probable_referent_said_as_an_assumption():
    AT = fresh()
    a = contact()
    wrote(a, AT - timedelta(minutes=12), voice=True)
    before = counts()
    r = digest.implicit_reference("Que sais-tu de cette personne ?", now=AT)
    assert r["kind"] == "probable" and r["people"][0]["entity_id"] == a["entity"]
    assert a["name"] in r["line"] and "hypothèse" in r["line"] and "confirmer" in r["line"]
    assert counts() == before                                  # nothing linked or written from a mention


def test_two_recent_contacts_make_it_ambiguous_and_a_group_or_an_old_message_is_not_a_referent():
    AT = fresh()
    a, b, g, old = contact(), contact(), contact(), contact()
    wrote(a, AT - timedelta(minutes=30))
    wrote(b, AT - timedelta(minutes=5))
    wrote(g, AT - timedelta(minutes=2), chat_type="group")
    wrote(old, AT - timedelta(hours=5))
    r = digest.implicit_reference("Il habite où maintenant ?", now=AT)
    assert r["kind"] == "ambiguous" and {p["entity_id"] for p in r["people"]} == {a["entity"], b["entity"]}
    assert "demander lequel" in r["line"]


def test_the_previous_exchange_naming_one_person_is_certain_and_two_are_ambiguous():
    AT = fresh()
    a, b, other = contact(), contact(), contact()
    wrote(other, AT - timedelta(minutes=3))
    r = digest.implicit_reference("Mets une tâche pour que je le relance le 10 décembre", now=AT,
                                  previous=f"Que sais-tu de {a['name']} ?", previous_age_s=120)
    assert r["kind"] == "certain" and r["people"][0]["entity_id"] == a["entity"] and "le relance" in r["line"]
    r2 = digest.implicit_reference("Tu peux le rappeler ?", now=AT, previous=f"{a['name']} et {b['name']} sont là",
                                   previous_age_s=60)
    assert r2["kind"] == "ambiguous"


def test_nothing_implicit_when_a_person_is_named_or_nobody_is_pointed_at():
    AT = fresh()
    a = contact()
    wrote(a, AT - timedelta(minutes=10))
    assert digest.implicit_reference(f"Que sais-tu de {a['name']} ?", now=AT) is None
    for m in ("Il fait chaud aujourd'hui ?", "Il y a combien de tâches ?", "Calcule 12 fois 7", "Merci !"):
        assert digest.implicit_reference(m, now=AT) is None, m


def test_the_main_models_context_says_the_reference_and_reads_that_persons_state(monkeypatch):
    AT = fresh()
    a = contact()
    monkeypatch.setattr(digest, "implicit_reference", lambda m, **kw: {
        "kind": "probable", "people": [{"entity_id": a["entity"], "name": a["name"], "basis": "inbound"}],
        "line": f"référence implicite probable : « cette personne » désigne sans doute « {a['name']} »"})
    r = context.get_context("Que sais-tu de cette personne ?", budget={"evidence": 0, "records": 0})
    assert a["name"] in r["sections"]["reference"] and r["trace"]["reference"]["kind"] == "probable"
    assert r["trace"]["state_plan"]["key"] == f"person:{a['entity']}"
    monkeypatch.setattr(digest, "implicit_reference", lambda m, **kw: {
        "kind": "ambiguous", "people": [], "line": "référence implicite ambiguë : demander lequel"})
    r = context.get_context("Que sais-tu de cette personne ?", budget={"evidence": 0, "records": 0})
    assert "demander lequel" in r["sections"]["reference"] and "state_plan" not in r["trace"]

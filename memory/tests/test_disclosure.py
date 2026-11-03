"""P1.7 on the test database: what may leave in an outgoing message — local_only never (GPS coordinates, places learned
from GPS), secrets never, commitments only with the owner's approval, third-party knowledge asked; the owner's own
channel is free; host adapters (Claude Code permission prompt, Hermes block/approve)."""
import json
import uuid

from walter_memory import disclosure, entities
from walter_memory.db import connection


def test_local_place_and_coordinates_never_leave():
    name = f"Résidence-{uuid.uuid4().hex[:5]}"
    with connection() as conn:
        entities.ensure(conn, "place", name, attributes={"lat": 13.7, "lng": 100.5, "wifis": [name]}, privacy_class="local_only")
    assert disclosure.check(f"Je suis chez moi, à {name}, passe quand tu veux", to="x@example.invalid", model=False)["action"] == "block"
    assert disclosure.check("rdv au 13.746012, 100.534077", to="x@example.invalid", model=False)["action"] == "block"


def test_commitment_needs_approval_but_not_for_the_owner_himself():
    r = disclosure.check("Ok pour samedi, je te rembourse les 300 euros", to="x@example.invalid", model=False)
    assert r["action"] == "ask" and r["reasons"][0]["rule"] == "commitment"
    assert disclosure.check("Merci, bien reçu.", to="x@example.invalid", model=False)["action"] == "allow"


def test_third_party_knowledge_is_asked():
    with connection() as conn:
        cid = conn.execute("""insert into kardex.contacts (canonical_name) values (%s) returning id""",
                           (f"Tiers {uuid.uuid4().hex[:4]}",)).fetchone()["id"]
        conn.execute("""insert into core.entities (entity_type, canonical_name, kardex_contact_id) values ('person', %s, %s)""",
                     (f"Tiers {cid}", cid))
        conn.execute("""insert into kardex.claims (contact_id, claim, claim_type, status) values (%s, %s, 'fact', 'active')""",
                     (cid, "Elle prépare un déménagement à Chiang Mai en décembre pour son nouveau travail"))
    r = disclosure.check("Au fait, elle prépare un déménagement à Chiang Mai en décembre pour son nouveau travail.",
                         to="autre@example.invalid", model=False)
    assert r["action"] == "ask" and any(x["rule"] == "third_party_knowledge" for x in r["reasons"])


def test_host_adapters(monkeypatch):
    from walter_memory import llm
    monkeypatch.setattr(llm, "decide", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no network in tests")))
    cc = disclosure.claude_code_hook({"tool_name": "mcp__g__send_message", "tool_input": {
        "to": "x@example.invalid", "body": "Je confirme le rendez-vous de mardi 15h et je paie l'acompte de 50 €."}})
    assert cc["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert disclosure.hermes_hook({"tool_input": {"action": "send", "target": "telegram", "message": "Rapport du jour"}}) is None
    h = disclosure.hermes_hook({"tool_input": {"action": "send", "target": "signal:+15550000000",
                                               "message": "D'accord pour vendredi, je t'envoie l'argent ce soir"}})
    assert h["action"] in ("approve", "block")

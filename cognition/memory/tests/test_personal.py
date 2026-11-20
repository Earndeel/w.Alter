"""Lot P2 (PROJECTIONS.md § 9): the personal and situational projections are reads — the owner's rules in force,
what holds until a date, his goals by their evidence, the transient states to re-check; where, the agenda, the open
work, each with its freshness. A cloud reader never gets a local row (counted, not rendered). No model is called."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import events, llm, personal, projection
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model")))


def tag() -> str:
    return uuid.uuid4().hex[:8]


def item(text, *, kind="constraint", subject="owner", epistemic="stated_owner", stage="stated", scope="durable",
         at=None, valid_to=None, privacy="cloud_allowed", domain=None, **attrs):
    at = at or NOW - timedelta(days=1)
    ev = events.record_events([{"event_type": "message.sent", "source": "claude_code", "source_account": "pytest",
                                "source_id": uuid.uuid4().hex, "thread_id": f"p2-{tag()}", "occurred_at": at,
                                "content": text, "privacy_class": privacy}])["event_ids"][0]
    a = {"subject": subject, **({"domain": domain} if domain else {}), **attrs}
    with connection() as conn:
        r = conn.execute("""insert into core.derived_items (kind, content, attributes, status, derived_by,
                                processor_version, source_event_ids, source_refs, valid_from, valid_to, privacy_class,
                                generation, epistemic, stage, scope)
                            values (%s, %s, %s, 'derived', 'l3.extract', '1', %s::uuid[], %s, %s, %s, %s, 'g1', %s, %s, %s)
                            returning item_id::text""",
                         (kind, text, json.dumps(a), [ev], json.dumps({"ref": f"p2:{tag()}"}), at, valid_to, privacy,
                          epistemic, stage, scope)).fetchone()["item_id"]
        conn.execute("update core.derived_items set lineage_id = item_id where item_id = %s", (r,))
    return r


def ids(lines):
    return {l["id"] for l in lines}


def test_keys_and_the_question_that_asks_for_the_owners_own_state():
    assert personal.kind_of("owner") == "owner" and personal.kind_of("Monsieur") == "owner"
    assert personal.kind_of("now") == "now" and personal.kind_of("me") == "me"
    assert personal.kind_of("project:walter") is None and personal.kind_of("Walter Memory") is None
    for q in ("Où en suis-je ?", "Quel est mon état courant personnel ?", "Qu'est-ce que j'ai en cours ?",
              "rappelle-moi mes engagements"):
        assert personal.ME_HINT.search(q), q
    assert not personal.ME_HINT.search("Où en est w.Alter ?")


def test_the_personal_state_is_his_rules_dated_states_and_goals_by_their_evidence():
    x = tag()
    rule = item(f"Monsieur ne veut jamais recevoir de commande à taper {x}", kind="constraint")
    again = item(f"Monsieur répète qu'il veut des réponses en français {x}", kind="correction")
    with connection() as conn:     # reaffirmed: a second source
        ev = events.record_events([{"event_type": "message.sent", "source": "claude_code", "source_account": "pytest",
                                    "source_id": uuid.uuid4().hex, "thread_id": "p2", "occurred_at": NOW,
                                    "content": "encore", "privacy_class": "cloud_allowed"}])["event_ids"][0]
        conn.execute("update core.derived_items set source_event_ids = source_event_ids || %s::uuid where item_id = %s",
                     (ev, again))
    task_rule = item(f"Pour cette tâche, garder le port {x}", kind="constraint", scope="task")
    agent_rule = item(f"W.Alter pense que Monsieur préfère le thé {x}", kind="constraint", epistemic="agent_reported")
    pref = item(f"Monsieur préfère les interfaces sur fond noir {x}", kind="preference")
    until = item(f"Monsieur est en déplacement jusqu'à vendredi {x}", kind="fact", scope="until",
                 valid_to=NOW + timedelta(days=2))
    gone = item(f"Monsieur était en congé {x}", kind="fact", scope="until", valid_to=NOW - timedelta(hours=1),
                at=NOW - timedelta(days=3))
    old_state = item(f"Monsieur est encore en train de déménager {x}", kind="fact", scope="task",
                     at=NOW - timedelta(days=12), epistemic="agent_reported")
    fact = item(f"Monsieur habite en France {x}", kind="fact")
    claimed = item(f"Monsieur demande de ranger ses factures {x}", kind="goal", stage="executed", scope="task",
                   at=NOW - timedelta(days=2))
    aim = item(f"Monsieur veut apprendre le piano {x}", kind="goal", stage="requested", at=NOW - timedelta(days=3))
    local = item(f"Monsieur ne parle jamais de sa santé {x}", kind="constraint", privacy="local_only")
    moved = item(f"Monsieur veut que sa boîte mail soit triée {x}", kind="constraint", subject="other",
                 domain="personal")
    elsewhere = item(f"Le projet Vela garde ses logs {x}", kind="constraint", subject="project:Vela")

    p = personal.personal()
    s = p["sections"]
    rules = ids(s["rules"])
    assert {rule, again, moved} <= rules and not {task_rule, agent_rule, local, elsewhere} & rules
    order = [l["id"] for l in s["rules"]]
    assert order.index(again) < order.index(rule)                 # reaffirmed first
    assert pref in ids(s["prefs"]) and until in ids(s["temporary"])
    assert gone not in {i for v in s.values() if isinstance(v, list) for i in ids(v)}     # expired: never current
    assert old_state in ids(s["reverify"]) and fact in ids(s["facts"])
    assert claimed in ids(s["goals"]["claimed"]) and aim in ids(s["aims"])
    assert p["withheld"] >= 1                                     # the local rule is counted
    # a local reader gets it
    assert local in ids(personal.personal(max_privacy="local_only")["sections"]["rules"])
    # at a date: the state as it was (the expired one held then)
    then = personal.personal(at=NOW - timedelta(days=2))
    assert gone in ids(then["sections"]["temporary"]) and fact not in ids(then["sections"]["facts"])

    text, shown = personal.render(p, None, max_tokens=20000)
    assert "[annoncé terminé, non vérifié]" in text and "À revérifier" in text and local not in shown
    assert f"santé {x}" not in text


def test_the_situation_says_where_what_is_on_the_agenda_and_what_is_open_never_a_local_row_to_the_cloud():
    x = tag()
    soon = NOW + timedelta(days=1)
    events.record_events([
        {"event_type": "calendar.event", "source": "calendar", "source_account": "pytest", "source_id": f"c1-{x}",
         "occurred_at": soon, "content": f"Dentiste {x}", "privacy_class": "cloud_allowed",
         "payload": {"event_id": f"c1-{x}", "start": {"dateTime": soon.isoformat()}, "status": "confirmed"}},
        {"event_type": "calendar.event", "source": "calendar", "source_account": "pytest", "source_id": f"c2-{x}",
         "occurred_at": soon, "content": f"Rendez-vous privé {x}", "privacy_class": "local_only",
         "payload": {"event_id": f"c2-{x}", "start": {"dateTime": soon.isoformat()}, "status": "confirmed"}},
        {"event_type": "calendar.event", "source": "calendar", "source_account": "pytest", "source_id": f"c3-{x}",
         "occurred_at": soon, "content": f"Annulé {x}", "privacy_class": "cloud_allowed",
         "payload": {"event_id": f"c3-{x}", "start": {"dateTime": soon.isoformat()}, "status": "cancelled"}},
        {"event_type": "location.sample", "source": "overland", "source_account": "pytest", "source_id": f"l-{x}",
         "occurred_at": NOW - timedelta(minutes=5), "content": None, "privacy_class": "local_only",
         "payload": {"lat": 1.234567, "lng": 2.345678, "accuracy_m": 10}}])
    s = personal.situation()
    titles = [r["content"] for r in s["agenda"]["week"]]
    assert f"Dentiste {x}" in titles and f"Annulé {x}" not in titles and f"Rendez-vous privé {x}" not in titles
    assert s["agenda"]["withheld"] >= 1 and s["place"] == {"status": "withheld"}
    text, _ = personal.render(None, s, max_tokens=20000)
    assert f"Dentiste {x}" in text and "privé" not in text and "1.23" not in text and "donnée locale" in text
    local = personal.situation(max_privacy="local_only")
    assert local["place"]["status"] == "recent"
    assert f"Rendez-vous privé {x}" in [r["content"] for r in local["agenda"]["week"]]


def test_memory_view_and_the_check_serve_the_personal_keys():
    item(f"Monsieur veut des réponses courtes {tag()}", kind="preference")
    r = projection.read({"key": "owner"})
    assert r["depth"] == "state" and r["content"].startswith("État personnel de Monsieur")
    me = projection.read({"key": "me", "max_tokens": 600})
    assert me["content"].startswith("Situation de Monsieur") and projection._tokens(me["content"]) <= 650
    assert projection.read({"key": "now", "at": "2026-11-12"}).get("error")
    c = projection.check(["owner"], limit_ms=5000)
    assert c["projects"][0]["key"] == "me" and not [p for p in c["projects"][0]["problems"] if "latence" not in p]


def test_p2_corrections_no_landmark_as_appointment_no_description_as_rule_no_request_as_aim_old_facts_dated():
    x = tag()
    soon = NOW + timedelta(days=1)
    events.record_events([
        {"event_type": "calendar.event", "source": "calendar", "source_account": "pytest", "source_id": f"h-{x}",
         "occurred_at": soon, "content": f"Jour férié {x}", "privacy_class": "cloud_allowed",
         "payload": {"event_id": f"h-{x}", "calendar_id": "fr.french#holiday@group.v.calendar.google.com",
                     "start": {"date": soon.date().isoformat()}}},
        {"event_type": "calendar.event", "source": "calendar", "source_account": "pytest", "source_id": f"w-{x}",
         "occurred_at": soon, "content": f"Semaine 47 {x}", "privacy_class": "cloud_allowed",
         "payload": {"event_id": f"w-{x}", "calendar_id": "e_2_fr#weeknum@group.v.calendar.google.com",
                     "start": {"date": soon.date().isoformat()}}},
        {"event_type": "calendar.event", "source": "calendar", "source_account": "pytest", "source_id": f"r-{x}",
         "occurred_at": soon, "content": f"Rendez-vous banque {x}", "privacy_class": "cloud_allowed",
         "payload": {"event_id": f"r-{x}", "calendar_id": "someone@gmail.com",
                     "start": {"dateTime": soon.isoformat()}}}])
    s = personal.situation()
    titles = [r["content"] for r in s["agenda"]["week"]]
    assert f"Rendez-vous banque {x}" in titles and f"Jour férié {x}" not in titles and f"Semaine 47 {x}" not in titles
    text, _ = personal.render(None, s, max_tokens=20000)
    assert f"jour férié : " in text and f"Semaine 47 {x}" not in text

    norm = item(f"Monsieur ne veut jamais de mot de passe dans un message {x}", kind="constraint")
    bio = item(f"Monsieur précise qu'il habite à Lyon depuis trois ans {x}", kind="correction")
    tech = item(f"Le service écoute sur :8890 avec /walter/cognition/memory/.env {x}", kind="constraint")
    request = item(f"Monsieur demande de vérifier les sauvegardes {x}", kind="goal", stage="requested")
    aim = item(f"Monsieur veut que W.Alter devienne autonome à terme {x}", kind="goal", stage="requested")
    old = item(f"Monsieur aime le jazz {x}", kind="fact", at=NOW - timedelta(days=60))
    p = personal.personal()
    sec = p["sections"]
    assert norm in ids(sec["rules"]) and bio not in ids(sec["rules"]) and tech not in ids(sec["rules"])
    assert bio in ids(sec["facts"]) and p["set_aside"]["technical"] >= 1
    assert request not in ids(sec["aims"]) and aim in ids(sec["aims"]) and p["set_aside"]["requests"] >= 1
    line = next(l for l in sec["facts"] if l["id"] == old)
    assert line["old"] and all(l["old"] for l in sec["facts"][sec["facts"].index(line):])     # the old ones last
    b = personal.blocks_owner({**p, "sections": {**sec, "facts": [line]}})
    assert "non reconfirmé depuis" in b["facts"][1][0][0] and "écartés de cet état" in b["facts"][2][-1]


def test_the_delay_of_personal_knowledge_says_its_cause_and_its_resumption():
    from walter_memory import extract2
    until = (NOW + timedelta(days=3)).isoformat()
    extract2.note_gate("provider_limit", {"reason": "limite réelle du fournisseur : HTTP 429", "until": until})
    with connection() as conn:
        first = conn.execute("select value->>'since' s from extraction.state where key = 'live_gate'").fetchone()["s"]
    extract2.note_gate("provider_limit", {"reason": "limite réelle du fournisseur : HTTP 429", "until": until})
    with connection() as conn:
        st = conn.execute("select value from extraction.state where key = 'live_gate'").fetchone()["value"]
    assert st["since"] == first and st["until"] == until               # the state lasts: its start is kept
    s = personal.situation()
    lines = [l for l, _ in personal.learned_lines(s["learned"], s["now"])]
    assert any("limite réelle du fournisseur" in l and "reprise automatique le" in l for l in lines), lines
    extract2.note_gate("open", {"ok": True})
    s = personal.situation()
    assert not any("limite réelle" in l for l, _ in personal.learned_lines(s["learned"], s["now"]))


def test_a_personal_statement_without_subject_is_the_owners():
    """The 19/11 format gives no subject: a personal statement went to « other » (P2 fix: it is the owner's)."""
    from walter_memory import extract2
    seg = [{"event_type": "message.sent", "content": "je préfère qu'on me tutoie"}]
    it, _ = extract2.validate({"type": "preference", "text": "Monsieur préfère être tutoyé", "domain": "personnel",
                               "msgs": [1], "quote": "je préfère qu'on me tutoie"}, seg, {})
    assert it["domain"] == "personal" and it["subject"] == "owner"
    rel, _ = extract2.validate({"type": "fait", "text": "Paul est son voisin", "domain": "relation", "msgs": [1],
                                "quote": "je préfère qu'on me tutoie"}, seg, {})
    assert rel["subject"] == "other"

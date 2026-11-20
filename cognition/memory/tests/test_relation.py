"""Lot P3 (PROJECTIONS.md § 10): the relational state of one person is a read of Kardex, the organic knowledge about
them, their relations and episodes — who says each thing, what changed, the exchanges as measures, the commitments,
what may need a follow-up (nothing is created), the contexts without duplication, the rhythm as numbers, the history
of what was replaced. Homonyms are listed, never merged. A cloud reader never gets a local row nor a sensitive
claim, whatever the owner's reasoning mode. No model is called."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import context, events, llm, projection, relation
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model")))


def tag() -> str:
    return uuid.uuid4().hex[:8]


def person(name, *, contact=True, messages=120):
    with connection() as conn:
        cid = conn.execute("insert into kardex.contacts (canonical_name, relationship_type, occupation) "
                           "values (%s, 'ami', 'architecte') returning id", (name,)).fetchone()["id"] if contact else None
        eid = conn.execute("""insert into core.entities (entity_type, canonical_name, kardex_contact_id)
                              values ('person', %s, %s) returning entity_id::text""", (name, cid)).fetchone()["entity_id"]
        for w, n in (("all", messages), ("30d", messages // 4), ("90d", messages // 2)):
            conn.execute("""insert into kardex.relationship_baselines (entity_id, window_name, messages, from_me, from_them,
                                msgs_per_day, initiation_ratio_me, median_reply_me_s, median_reply_them_s,
                                first_contact, last_contact, processor_version)
                            values (%s, %s, %s, %s, %s, 2.0, 0.5, 120, 300, %s, %s, 'pytest')""",
                         (eid, w, n, n // 2, n - n // 2, NOW - timedelta(days=200), NOW - timedelta(days=1)))
    return eid, cid


def claim(cid, text, *, ctype="work", status="proposed", origin="direct_statement", sens="normal",
          disclosure="explicitly_told_me", supersedes=None, created=None):
    with connection() as conn:
        return conn.execute("""insert into kardex.claims (contact_id, claim_type, claim, status, knowledge_origin,
                                   disclosure_state, mention_policy, sensitivity, supersedes_claim_id, created_at, updated_at)
                               values (%s, %s, %s, %s, %s, %s, 'contextual_only', %s, %s, %s, %s) returning id""",
                            (cid, ctype, text, status, origin, disclosure, sens, supersedes, created or NOW - timedelta(days=2),
                             created or NOW - timedelta(days=2))).fetchone()["id"]


def known(eid, text, *, kind="fact", by="l3.extract", epistemic="stated_owner", privacy="cloud_allowed", at=None,
          status="derived", **attrs):
    at = at or NOW - timedelta(days=1)
    ev = events.record_events([{"event_type": "message.sent", "source": "claude_code", "source_account": "pytest",
                                "source_id": uuid.uuid4().hex, "thread_id": f"p3-{tag()}", "occurred_at": at,
                                "content": text, "privacy_class": privacy}])["event_ids"][0]
    with connection() as conn:
        r = conn.execute("""insert into core.derived_items (kind, content, attributes, status, derived_by, processor_version,
                                source_event_ids, source_refs, valid_from, privacy_class, generation, epistemic, stage,
                                scope, subject_entity_ids, created_at)
                            values (%s, %s, %s, %s, %s, '1', %s::uuid[], %s, %s, %s, 'g1', %s, 'stated', 'durable',
                                    %s::uuid[], %s) returning item_id::text""",
                         (kind, text, json.dumps(attrs), status, by, [ev], json.dumps({"ref": f"p3:{tag()}"}), at, privacy,
                          epistemic, [eid], at)).fetchone()["item_id"]
        conn.execute("update core.derived_items set lineage_id = item_id where item_id = %s", (r,))
    return r


def test_homonyms_are_listed_never_merged_and_an_id_resolves_one():
    name = f"Léa Homonyme {tag()}"
    a, _ = person(name, messages=300)
    b, _ = person(name, contact=False, messages=40)
    s = relation.state(f"person:{name}")
    assert {c["entity_id"] for c in s["ambiguous"]} == {a, b}
    text, shown = relation.render(s)
    assert "désigne 2 personnes" in text and "jamais fusionnées" in text and not shown
    one = relation.state(f"person:{a[:8]}")
    assert one["entity_id"] == a
    assert relation.state(f"person:Personne Inexistante {tag()}").get("missing")


def test_who_says_it_privacy_and_no_psychological_conclusion():
    x = tag()
    eid, cid = person(f"Paul Source {x}")
    said = claim(cid, f"Paul dit travailler dans un cabinet {x}")
    sure = claim(cid, f"Paul est un ami d'enfance {x}", ctype="social_circle", status="confirmed")
    secret = claim(cid, f"Paul a un souci de santé {x}", ctype="health", sens="highly_sensitive")
    typed = claim(cid, f"Paul a parlé de ses préférences {x}", ctype="sexual_preference")
    mine = known(eid, f"Monsieur dit que Paul l'aide sur ses plans {x}")
    local = known(eid, f"Conversation privée {x}", by="flows.conversations", epistemic="observed", privacy="local_only",
                  messages=12, owner_messages=5, network="whatsapp")
    known(eid, f"Conversation {x}", by="flows.conversations", epistemic="observed", privacy="redacted_cloud",
          messages=8, owner_messages=3, network="whatsapp", at=NOW - timedelta(days=3))
    with connection() as conn:
        conn.execute("""insert into kardex.communication_deviations (entity_id, metric, baseline, current, ratio,
                            baseline_window, current_window, sample_size, observation, processor_version)
                        values (%s, 'msgs_per_day', 2.0, 0.4, 0.2, '90d', '14d', 120, 'mesure', 'pytest')""", (eid,))
    s = relation.state(eid)
    lines = {x["id"]: x for x in s["claims"]["current"] + s["items"]["statements"]}
    assert lines[f"k{said}"]["who"] == "dit par la personne" and lines[f"k{sure}"]["who"] == "confirmé par Monsieur"
    assert lines[mine]["who"] == "dit par Monsieur"
    assert f"k{secret}" not in lines and f"k{typed}" not in lines and s["withheld"] >= 3     # counted, not shown
    assert len(s["items"]["conversations"]) == 1                                             # the local one: counted
    text, shown = relation.render(s, max_tokens=20000)
    assert "santé" not in text and "privée" not in text and local not in shown
    assert "vérifié par les données" in text and "8 messages dont 3 de Monsieur" in text
    assert "messages par jour 2.0 → 0.4" in text and "cause inconnue" in text
    for word in ("froid", "distant", "fâché", "triste", "s'éloigne", "désintérêt"):
        assert word not in text
    # a local reader gets what the owner sees
    loc = relation.state(eid, max_privacy="local_only")
    assert f"k{secret}" in {x["id"] for x in loc["claims"]["current"]} and len(loc["items"]["conversations"]) == 2
    # the owner's « oui tout » reasoning mode does not open a projection to sensitive claims
    import walter_memory.read_policy as rp
    orig = rp._reasoning_full
    rp._reasoning_full = lambda: True
    try:
        assert f"k{secret}" not in {x["id"] for x in relation.state(eid)["claims"]["current"]}
    finally:
        rp._reasoning_full = orig


def test_a_changed_situation_keeps_its_history_and_reads_as_it_was():
    x = tag()
    eid, cid = person(f"Nora Change {x}")
    old = claim(cid, f"Nora travaille à Lyon {x}", status="superseded", created=NOW - timedelta(days=20))
    new = claim(cid, f"Nora travaille désormais à Paris {x}", supersedes=old, created=NOW - timedelta(days=2))
    contra = claim(cid, f"Nora travaille encore à Lyon {x}", created=NOW - timedelta(days=1))   # a contradiction: both said
    with connection() as conn:
        conn.execute("update kardex.claims set updated_at = %s where id = %s", (NOW - timedelta(days=2), old))
    s = relation.state(eid)
    cur = {x["id"] for x in s["claims"]["current"]}
    assert f"k{new}" in cur and f"k{contra}" in cur and f"k{old}" not in cur   # never silently resolved
    h = {x["id"]: x for x in s["claims"]["history"]}
    assert h[f"k{old}"]["how"] == "remplacé" and h[f"k{old}"]["replaced_by"] == f"k{new}"
    text, _ = relation.render(s, max_tokens=20000)
    assert "Historique (informations remplacées, conservées)" in text and f"→ k{new}" in text
    then = relation.state(eid, at=NOW - timedelta(days=10))
    assert f"k{old}" in {x["id"] for x in then["claims"]["current"]}
    assert f"k{new}" not in {x["id"] for x in then["claims"]["current"]}
    gone = known(eid, f"Nora habite chez ses parents {x}", status="superseded", at=NOW - timedelta(days=9))
    assert gone in {x["id"] for x in relation.state(eid)["items"]["history"]}


def test_one_person_in_several_projects_commitments_and_follow_ups_without_any_write():
    x = tag()
    eid, cid = person(f"Marc Projets {x}")
    with connection() as conn:
        for n in (f"Projet Alpha {x}", f"Projet Beta {x}"):
            pid = conn.execute("insert into core.entities (entity_type, canonical_name) values ('project', %s) "
                               "returning entity_id", (n,)).fetchone()["entity_id"]
            for _ in range(2):            # stated twice: still one context
                conn.execute("""insert into core.relationships (subject_id, predicate, object_id, generation, privacy_class)
                                values (%s, 'works_on', %s, 'g1', 'cloud_allowed')""", (eid, pid))
        conn.execute("""insert into kardex.open_loops (contact_id, loop_type, description, status, deadline_at)
                        values (%s, 'action_item', %s, 'open', %s)""", (cid, f"Lui renvoyer le devis {x}",
                                                                         NOW - timedelta(days=1)))
    plan = known(eid, f"Dîner prévu avec Marc {x}", kind="plan", by="episodic.plans",
                 start=(NOW + timedelta(days=3)).isoformat(), agreed=True)
    with connection() as conn:
        before = conn.execute("select (select count(*) from core.derived_items) d, (select count(*) from kardex.actions) a, "
                              "(select count(*) from bus.events) b").fetchone()
    s = relation.state(eid)
    assert s["contexts"]["projects"] == sorted([f"Projet Alpha {x}", f"Projet Beta {x}"])
    assert plan in {p["id"] for p in s["items"]["plans"]}
    whys = [f["why"] for f in s["follow_up"]]
    assert any(w.startswith("échéance passée") for w in whys) and any(w.startswith("prévu le") for w in whys)
    text, _ = relation.render(s, max_tokens=20000)
    assert "rien n'est créé ni envoyé" in text and "[convenu, le" in text and text.count(f"Projet Alpha {x}") == 1
    with connection() as conn:
        after = conn.execute("select (select count(*) from core.derived_items) d, (select count(*) from kardex.actions) a, "
                             "(select count(*) from bus.events) b").fetchone()
    assert before == after                                       # a read: no task, no notification, no action
    done = known(eid, f"Marc est allé voir le chantier {x}", kind="commitment")
    with connection() as conn:
        conn.execute("update core.derived_items set stage = 'executed' where item_id = %s", (done,))
    s = relation.state(eid)                                     # a carried-out action is a past fact, not a plan
    assert done not in {p["id"] for p in s["items"]["plans"]} and done in {p["id"] for p in s["items"]["statements"]}


def test_memory_view_check_and_context_serve_the_relation(monkeypatch):
    x = tag()
    name = f"Zoé Contexte{x}"
    eid, cid = person(name, messages=200)
    claim(cid, f"Zoé dit qu'elle aime l'escalade {x}", ctype="hobby")
    r = projection.read({"key": f"person:{eid[:8]}", "depth": "state"})
    assert r["content"].startswith(f"Relation avec {name}") and r["ms"] < 1000
    c = projection.check([f"person:{eid[:8]}"], limit_ms=5000)
    assert c["projects"][0]["ok"], c
    assert relation.REL_HINT.search(f"Où en est ma relation avec {name} ?")
    context._names_cache = None
    out = context.get_context(f"Où en est ma relation avec {name} ?", include_profile=False)
    st = out["trace"]["sections"]["state"]
    assert st["key"] == f"person:{eid}" and st["tokens"] <= st["budget"]
    assert "Relation avec" in out["sections"]["state"]

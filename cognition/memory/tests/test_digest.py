"""The situation digest (PROJECTIONS.md § 11): what Memory knows of ONE message's references, for the preflight's
single Decision call. Adaptive (nothing when nothing is referred to), within its budget, dated, from the existing
projections; homonyms said ambiguous, never resolved; the position as a signal, never the place; texts masked for a
cloud reader; a read: no model, no write."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from test_projection import filler, item, projects  # noqa: F401 — fixture reused
from test_relation import person
from walter_memory import digest, events, llm, personal
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the digest never calls a model")
    monkeypatch.setattr(llm, "chat", boom)
    monkeypatch.setattr(llm, "decide", boom)


def test_a_message_without_reference_gets_nothing():
    for m in ("Quelle est la capitale de l'Australie ?", "Écris une regex pour un code postal.",
              "Combien de jours entre le 3 mars et le 19 avril ?"):
        d = digest.build(m)
        assert d["lines"] == [] and d["tokens"] == 0 and digest.block(d) is None


def test_a_named_project_is_one_dated_line_not_repeated_after_a_recent_exchange(projects):   # noqa: F811
    p = projects["parent"]
    filler(p, 6)
    item(f"{p} est en ligne depuis lundi", p, NOW - timedelta(days=1), kind="state")
    d = digest.build(f"Où en est {p} ?")
    assert d["kinds"] == ["project"] and f"« {p} »" in d["lines"][0] and "dernière activité" in d["lines"][0]
    assert d["tokens"] <= 250
    again = digest.build(f"Et {p}, c'est stable ?", previous=f"Fais le point sur {p}", previous_age_s=300)
    assert "project" not in again["kinds"] and again["known"] == 1          # already in front of the decision
    old = digest.build(f"Et {p}, c'est stable ?", previous=f"Fais le point sur {p}", previous_age_s=86400)
    assert "project" in old["kinds"]


def test_a_project_switch_is_said_as_a_fact(projects):                                 # noqa: F811
    a, b = projects["parent"], projects["child"]
    filler(a, 6)
    filler(b, 6)
    d = digest.build(f"Passons à {b} : la suite ?", previous=f"Où en est {a} tout seul ?", previous_age_s=600)
    if "switch" in d["kinds"]:                       # the child's name contains the parent's: never a false switch
        pytest.fail("a sub-project named like its parent is no switch")
    x = projects["x"]
    other = f"Quartz{x}"
    filler(other, 6)
    from walter_memory import projection
    projection._catalog_memo.clear()
    d = digest.build(f"Passons à {other} : la suite ?", previous=f"Où en est {a} ?", previous_age_s=600)
    assert "switch" in d["kinds"]
    assert any(l.startswith("l'échange précédent nommait") for l in d["lines"])


def _letters() -> str:
    return "".join(chr(97 + int(c, 16)) for c in uuid.uuid4().hex[:6])


def test_a_name_several_people_bear_is_ambiguous_never_resolved():
    from walter_memory import context
    context._names_cache = None
    name = f"Ilan Double{_letters()}"
    person(name, messages=300)
    person(name, contact=False, messages=40)
    d = digest.build(f"Qu'est-ce que {name} m'a dit ?")
    assert d["kinds"] == ["person"] and "ambigu, 2 personnes" in d["lines"][0] and "jamais fusionnées" in d["lines"][0]
    one = f"Oriane Unique{_letters()}"
    person(one, messages=200)
    d = digest.build(f"Résume mes échanges avec {one}")
    assert d["kinds"] == ["person"] and "200 messages" in d["lines"][0] and "fiche Kardex" in d["lines"][0]
    assert "ami" not in d["lines"][0] and "architecte" not in d["lines"][0]   # the card's fields stay out


def test_the_position_is_a_signal_never_the_place():
    x = uuid.uuid4().hex[:6]
    lat, lng = 13.7311, 100.5232
    events.record_events([{"event_type": "location.sample", "source": "overland", "source_account": "pytest",
                           "source_id": uuid.uuid4().hex, "occurred_at": NOW - timedelta(minutes=2),
                           "privacy_class": "local_only",
                           "payload": {"lat": lat, "lng": lng, "accuracy_m": 8, "raw": {"properties": {}}}}])
    with connection() as conn:
        conn.execute("""insert into core.entities (entity_type, canonical_name, attributes)
                        values ('place', %s, %s::jsonb)""", (f"Rue Secrète {x}", f'{{"lat": {lat}, "lng": {lng}}}'))
    d = digest.build("Y a une pharmacie ouverte près d'ici ?")
    assert d["kinds"] == ["position"]
    line = d["lines"][0]
    assert "une position est connue" in line and "Secrète" not in line
    assert "13.7" not in line and "100.5" not in line


def test_resumed_work_lists_open_tasks_masked_and_never_a_flagged_text(monkeypatch):
    monkeypatch.setattr(personal, "_tasks", lambda limit=8: [
        {"goal": "Appeler le +33 6 12 34 56 78 pour le devis", "status": "open", "updated_at": NOW.isoformat()},
        {"goal": "Finir la migration du portail", "status": "suspended", "updated_at": NOW.isoformat()},
        {"goal": "Clore le ticket", "status": "done", "updated_at": NOW.isoformat()}])
    d = digest.build("Bon, on reprend où on en était ?")
    assert d["kinds"] == ["tasks"]
    line = d["lines"][0]
    assert "12 34 56 78" not in line and "migration du portail" in line and "Clore le ticket" not in line
    named = digest.build("On reprend Quartzzz ?")              # an unknown name: still a resumption
    assert "tasks" in named["kinds"]


def test_the_budget_is_a_ceiling_and_the_digest_writes_nothing(monkeypatch):
    monkeypatch.setattr(personal, "_tasks", lambda limit=8: [
        {"goal": f"Tâche numéro {i} avec un intitulé assez long pour peser", "status": "open",
         "updated_at": NOW.isoformat()} for i in range(4)])
    with connection() as conn:
        before = conn.execute("select (select count(*) from core.derived_items) d, (select count(*) from bus.events) b, "
                              "(select count(*) from core.events) e").fetchone()
    d = digest.build("Où j'en suis de mes engagements ? on reprend demain près d'ici", max_tokens=120)
    assert d["tokens"] <= 120 and d["cut"] >= 1 and d["lines"]
    full = digest.build("Où j'en suis de mes engagements ? on reprend demain près d'ici")
    assert full["tokens"] <= 250 and {"tasks", "agenda", "position"} <= set(full["kinds"])
    with connection() as conn:
        after = conn.execute("select (select count(*) from core.derived_items) d, (select count(*) from bus.events) b, "
                             "(select count(*) from core.events) e").fetchone()
    assert before == after

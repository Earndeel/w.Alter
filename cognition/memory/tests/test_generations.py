"""Memory generations (P1.0), test database: V1 knowledge is never contaminated by pre-V1 interpretations; what Walter
reads does not change before the switch; after a (simulated) switch pre-V1 knowledge leaves the default context but
stays available on an explicit history request; canonical evidence is never hidden; rollback restores today."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from walter_memory import context, events, extract2, generations, ingestion, organic, search, views
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)
TAG = uuid.uuid4().hex[:6]


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(search, "_rerank", lambda q, results, limit, timeout=8: results[:limit])
    ingestion.register_connector("search_indexer", "walter", "agent", "pytest", timedelta(minutes=10))
    extract2.set_v1_start(NOW - timedelta(days=1))
    generations.rollback(confirm=True)          # every test starts from today's state: g0 active, both readable
    yield
    generations.rollback(confirm=True)


def event(text, source="hermes", thread=None):
    return events.record_events([{"event_type": "message.sent", "source": source, "source_account": "pytest",
                                  "source_id": uuid.uuid4().hex, "thread_id": thread or f"t-{uuid.uuid4().hex[:8]}",
                                  "occurred_at": NOW - timedelta(hours=3), "content": text,
                                  "privacy_class": "cloud_allowed"}])["event_ids"][0]


def legacy_item(text, eid, derived_by="hindsight"):
    """A pre-V1 interpretation, written the way old producers write (no generation given)."""
    with connection() as conn:
        return conn.execute("""insert into core.derived_items (kind, content, status, derived_by, source_event_ids,
                                   privacy_class) values ('memory', %s, 'legacy_derived', %s, %s::uuid[], 'cloud_allowed')
                               returning item_id::text, generation""", (text, derived_by, [eid])).fetchone()


def v1_item(text, thread):
    eid = event(text, "claude_code", thread)

    def model(messages, **kw):
        return {"content": json.dumps({"summary": "", "items": [
            {"kind": "decision", "text": text, "state": "decided", "msgs": [1], "quote": text[:60]}]}),
            "cost_usd": 0, "model": "scripted"}
    extract2.process_thread("claude_code", thread, chat=model, force=True)
    with connection() as conn:
        return conn.execute("""select item_id::text, generation from core.derived_items where derived_by = 'l3.extract'
                               and source_refs->>'thread' = %s and kind = 'decision'""", (thread,)).fetchone(), eid


def test_classification_and_safe_default():
    eid = event(f"note {TAG}")
    old = legacy_item(f"souvenir hindsight {TAG}", eid)
    assert old["generation"] == "g0"                               # a producer that says nothing writes history
    new, _ = v1_item(f"Le projet Orque{TAG} utilisera Postgres comme base unique", f"v1-{TAG}")
    assert new["generation"] == "g1"


def test_v1_cannot_cite_or_replace_pre_v1_knowledge():
    eid = event(f"ancien {TAG}")
    old = legacy_item(f"Le projet Baleine{TAG} utilise MySQL", eid)
    new, _ = v1_item(f"Le projet Baleine{TAG} passe à Postgres", f"guard-{TAG}")
    for role in ("supports", "supersedes", "contradicts"):
        with pytest.raises(psycopg.errors.RaiseException):
            with connection() as conn:
                conn.execute("""insert into core.provenance (target_table, target_id, source_type, source_id, role)
                                values ('derived_items', %s, 'derived', %s, %s)""", (new["item_id"], old["item_id"], role))
    with connection() as conn:   # the bootstrap's explicit bridge only
        conn.execute("""insert into core.provenance (target_table, target_id, source_type, source_id, role)
                        values ('derived_items', %s, 'derived', %s, 'imported_from')""", (new["item_id"], old["item_id"]))


def test_extraction_never_sees_pre_v1_knowledge_as_known():
    thread = f"known-{TAG}"
    eid = event(f"Pour le projet Dauphin{TAG}, on garde Redis", "claude_code", thread)
    legacy_item(f"Pour le projet Dauphin{TAG}, on garde Redis (souvenir hindsight)", eid)
    seen = []

    def model(messages, **kw):
        seen.append(messages[0]["content"])
        return {"content": json.dumps({"summary": "", "items": []}), "cost_usd": 0, "model": "scripted"}
    extract2.process_thread("claude_code", thread, chat=model, force=True)
    known = seen[0].split("Connaissances déjà enregistrées (références K) :", 1)[1].split("Messages à analyser", 1)[0]
    assert "souvenir hindsight" not in known


def _knowledge(q, **kw):
    search.index_pending()
    return context.get_context(q, include_profile=False, **kw)


def test_reads_unchanged_before_switch_then_history_only_after_and_rollback():
    eid = event(f"Le serveur Narval{TAG} tourne sous Debian depuis mars")    # canonical evidence
    old = legacy_item(f"Le serveur Narval{TAG} tourne sous Debian (souvenir pré-V1)", eid)
    new, _ = v1_item(f"Le serveur Narval{TAG} migrera vers Ubuntu", f"read-{TAG}")
    q = f"Sur quel système tourne le serveur Narval{TAG} ?"
    today = _knowledge(q)["text"]
    assert "souvenir pré-V1" in today and "migrera vers Ubuntu" in today          # today: both read, as before
    assert "— pré-V1" not in today                                                 # and nothing relabelled

    assert generations.switch("g1")["refused"]                                     # never without confirmation
    assert generations.switch("g1", confirm=True)["readable"] == ["g1"]
    after = _knowledge(q)["text"]
    assert "migrera vers Ubuntu" in after and "souvenir pré-V1" not in after
    ev = search.search(f"serveur Narval{TAG} Debian", include_derived=False, limit=5)
    assert any(r["ref_id"] == eid for r in ev)                                    # evidence is never hidden
    hist = _knowledge(q, history=True)["text"]
    assert "souvenir pré-V1" in hist and "— pré-V1)" in hist                       # on demand, labelled

    generations.rollback(confirm=True)
    assert "souvenir pré-V1" in _knowledge(q)["text"]


def test_switch_off_means_no_generation_filter(monkeypatch):
    eid = event(f"Le robot Mérou{TAG} est en panne")
    legacy_item(f"Le robot Mérou{TAG} est en panne (souvenir pré-V1)", eid)
    generations.switch("g1", confirm=True)
    monkeypatch.setattr(organic, "settings", lambda: {"generations": {"enforce": False}})
    assert generations.read_set() is None
    assert "souvenir pré-V1" in _knowledge(f"état du robot Mérou{TAG}")["text"]


def test_index_carries_the_generation():
    eid = event(f"chunk {TAG}")
    old = legacy_item(f"Le lac Saumon{TAG} gèle en janvier", eid)
    search.index_pending()
    with connection() as conn:
        g = conn.execute("select generation from search.chunks where kind = 'derived' and ref_id = %s",
                         (old["item_id"],)).fetchone()["generation"]
        e = conn.execute("select generation from search.chunks where kind = 'event' and ref_id = %s", (eid,)).fetchone()
    assert g == "g0" and e["generation"] is None


def test_views_follow_the_readable_generations():
    key = f"pytest-view-{TAG}"
    with connection() as conn:
        conn.execute("insert into views.view (view_key, domain, horizon, title, last_at) values (%s, 'projects', 'medium', 't', now())",
                     (key,))
        conn.execute("""insert into views.version (view_key, depth, version, content, builder)
                        values (%s, 'overview', 1, 'carte pré-V1', 'pytest')""", (key,))
    assert views.read({"depth": "overview", "key": key}).get("content") == "carte pré-V1"
    generations.switch("g1", confirm=True)
    assert "error" in views.read({"depth": "overview", "key": key})
    assert views.read({"depth": "overview", "key": key, "history": True}).get("content") == "carte pré-V1"


def _mode(read="g1_first", gate=6, slots=3):
    return {"read": read, "g0_gate": gate, "g0_slots": slots, "g0_candidates": 60}


def test_g1_first_consults_g0_only_when_it_wins_and_never_as_a_paraphrase(monkeypatch):
    """Read mode g1_first (2026-11-10): g1 is the memory; a g0 row enters only when it ranks among the best g0_gate
    knowledge candidates of the single rerank (here: rows about this run's cat first, then the pool order, so g1 rows
    rank first among them — the test database outlives a run: other rows must rank as a reranker would rank them)."""
    me = f"Roquefort{TAG}"
    monkeypatch.setattr(search, "_rerank", lambda q, results, limit, timeout=8:
                        sorted(results, key=lambda r: me not in (r.get("content") or r.get("text") or ""))[:limit])
    eid = event(f"Le chat Roquefort{TAG} aime le saumon")
    legacy_item(f"Le chat Roquefort{TAG} de Monsieur aime le saumon (souvenir pré-V1)", eid)
    q = f"Qu'aime manger le chat Roquefort{TAG} ?"
    monkeypatch.setattr(generations, "_mode_override", _mode())
    thin = _knowledge(q)
    mine = f"Roquefort{TAG} de Monsieur aime le saumon (souvenir pré-V1)"
    assert mine in thin["text"]                                    # g1 knows nothing: the old knowledge is consulted
    assert thin["trace"]["g0_fallback"]["kept"] >= 1
    facts = ["mange des croquettes au poulet le matin", "boit uniquement de l'eau filtrée", "refuse le thon en boîte",
             "adore les crevettes grises le dimanche", "a un vétérinaire à Lyon", "dort sur le canapé du salon",
             "ne supporte pas le lait"]
    for k, f in enumerate(facts):                                  # g1 now holds better-ranked knowledge on it
        v1_item(f"Le chat Roquefort{TAG} {f}", f"cat-{TAG}-{k}")
    full = _knowledge(q)
    assert mine not in full["text"] and f"Roquefort{TAG} ne supporte pas le lait" in full["text"]
    monkeypatch.setattr(generations, "_mode_override", _mode("all"))
    assert mine in _knowledge(q)["text"]                           # read = all: today's behaviour, unchanged


def test_g1_first_never_applies_to_history_requests(monkeypatch):
    eid = event(f"La barque Turbot{TAG} est bleue")
    legacy_item(f"La barque Turbot{TAG} est bleue (souvenir pré-V1)", eid)
    monkeypatch.setattr(generations, "_mode_override", _mode(gate=1, slots=1))
    res = _knowledge(f"couleur de la barque Turbot{TAG}", history=True)
    assert "g0_fallback" not in res["trace"] and "souvenir pré-V1" in res["text"]

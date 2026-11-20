"""Purge policy (cleanup phase 2, 2026-11-09): a purge covers the active database (events, knowledge, views, index,
walter_logs), leaves tombstones so ingestion cannot bring the data back, writes a ledger outside the database, and a
restore of older data is detected (verify) and undone (reapply). Synthetic data only, in the throwaway test database;
the ledger goes to a temporary file (conftest)."""
import json
import uuid
from datetime import datetime, timezone

from walter_memory import events, logs, purge
from walter_memory.db import connect

RUN = uuid.uuid4().hex[:10]
SECRET = f"Zq9-synthetic-{RUN}"
AT = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


def _ev(n, text):
    return {"event_type": "note.recorded", "source": "test", "source_id": f"purge-{RUN}-{n}", "occurred_at": AT,
            "content": text, "payload": {}, "privacy_class": "cloud_allowed"}


def test_purge_reingest_restore_reapply():
    ids = events.record_events([_ev(1, f"le code est {SECRET}"), _ev(2, "rien de secret ici")])["event_ids"]
    secret_id, other_id = ids
    with connect() as conn:
        item = conn.execute("""insert into core.derived_items (kind, content, status, derived_by, source_event_ids)
                               values ('fact', 'synthetic fact', 'derived', 'pytest', %s::uuid[]) returning item_id""",
                            ([secret_id],)).fetchone()["item_id"]
        older = conn.execute("""insert into core.derived_items (kind, content, status, derived_by, source_event_ids,
                                    valid_to, attributes) values ('fact', 'the fact it replaced', 'superseded', 'pytest',
                                    %s::uuid[], now(), %s) returning item_id""",
                             ([other_id], json.dumps({"superseded_by": str(item), "superseded_how": "replaces"}))
                             ).fetchone()["item_id"]
        seg = conn.execute("""insert into extraction.segments (processor, version, source, thread_id, status, event_ids,
                                  rejected) values ('l3.extract', 'pytest', 'test', %s, 'extracted', %s::uuid[], %s)
                              returning segment_id""", (f"purge-{RUN}", [secret_id, other_id],
                                                        json.dumps([{"quote": SECRET}]))).fetchone()["segment_id"]
        view = f"pytest:{RUN}"
        conn.execute("insert into views.view (view_key, domain, horizon, title, status) values (%s, 'projects', 'long', 't', 'active')", (view,))
        conn.execute("""insert into views.version (view_key, depth, version, content, builder, built_at)
                        values (%s, 'overview', 1, 'version d''avant cette connaissance', 'pytest', now() - interval '1 day')""",
                     (view,))
        conn.execute("""insert into views.version (view_key, depth, version, content, builder)
                        values (%s, 'overview', 2, %s, 'pytest')""", (view, f"résumé citant {SECRET}"))
        conn.execute("""insert into views.version (view_key, depth, version, content, builder)
                        values (%s, 'overview', 3, 'résumé des autres jours, sans rien de purgé', 'pytest')""", (view,))
        conn.execute("""insert into views.evidence (view_key, ref_kind, ref_id, role, privacy_class, added_by)
                        values (%s, 'derived', %s, 'support', 'cloud_allowed', 'pytest')""", (view, str(item)))
        conn.execute("""insert into search.chunks (kind, ref_id, chunk_no, occurred_at, source, label, text, tsv, privacy_class, indexer_version)
                        values ('event', %s, 0, %s, 'test', 'note', %s, to_tsvector('simple', %s), 'cloud_allowed', 'pytest')""",
                     (secret_id, AT, SECRET, SECRET))
        w = logs.Writer(conn)
        w.session(f"claude_code/pytest/{RUN}", runtime="claude_code", native_id=RUN)
        w.add(f"claude_code/pytest/{RUN}", "user/message", AT, "l1", text=f"voici {SECRET}", human=True)
        w.flush()
        backup = conn.execute("select * from core.events where event_id = %s", (secret_id,)).fetchone()

    dry = purge.purge(reason="pytest", requested_by="pytest", pattern=SECRET)
    assert dry["counts"] == {"events": 1, "derived": 1, "objects": 0, "walter_logs": 1,
                             "views_masked": 1, "view_versions_masked": 1,
                             "knowledge_restored": 1}                     # announced before executing
    done = purge.purge(reason="pytest", requested_by="pytest", pattern=SECRET, execute=True)
    assert done["status"] == "executed" and all(not b["automatic_change"] for b in done["backups"])
    with connect() as conn:
        assert conn.execute("select count(*) n from core.events where event_id = %s", (secret_id,)).fetchone()["n"] == 0
        assert conn.execute("select count(*) n from core.events where event_id = %s", (other_id,)).fetchone()["n"] == 1
        assert conn.execute("select count(*) n from core.derived_items where item_id = %s", (item,)).fetchone()["n"] == 0
        assert conn.execute("select count(*) n from search.chunks where ref_id = %s", (secret_id,)).fetchone()["n"] == 0
        v = conn.execute("select content, stale_since from views.version where view_key = %s and version = 2",
                         (view,)).fetchone()
        assert SECRET not in v["content"] and v["stale_since"] is not None
        old = conn.execute("select content from views.version where view_key = %s and version = 1", (view,)).fetchone()
        assert old["content"] == "version d'avant cette connaissance"     # built before it existed: never masked
        later = conn.execute("select content from views.version where view_key = %s and version = 3", (view,)).fetchone()
        assert later["content"] == "résumé des autres jours, sans rien de purgé"   # built after, quotes none of it: kept
        sg = conn.execute("select event_ids, rejected from extraction.segments where segment_id = %s", (seg,)).fetchone()
        assert [str(x) for x in sg["event_ids"]] == [str(other_id)] and sg["rejected"] == []    # an extracted message can be purged too
        back = conn.execute("select status, valid_to, attributes from core.derived_items where item_id = %s",
                            (older,)).fetchone()                              # what it had replaced is current again
        assert back["status"] == "derived" and back["valid_to"] is None and "superseded_by" not in back["attributes"]
        wl = conn.execute("select text, event_key from walter_logs.events where session_id = %s",
                          (f"claude_code/pytest/{RUN}",)).fetchone()
        assert wl["text"] == purge.MARK and wl["event_key"]
        # tombstones: the idempotence key stays
        assert conn.execute("select count(*) n from core.event_keys where event_id = %s", (secret_id,)).fetchone()["n"] == 1
    ledger_lines = [json.loads(x) for x in purge.ledger_path().read_text().splitlines()]
    assert {e["kind"] for e in ledger_lines if e["purge_id"] == done["purge_id"]} == {"event", "derived", "walter_logs"}
    assert SECRET not in purge.ledger_path().read_text()                     # identifiers only, never the pattern

    # ingestion cannot bring it back: the connector re-reads its source
    assert events.record_events([_ev(1, f"le code est {SECRET}")])["inserted"] == 0
    with connect() as conn:                                                     # nor the journal's writer
        w = logs.Writer(conn)
        w.session(f"claude_code/pytest/{RUN}", runtime="claude_code", native_id=RUN)
        w.add(f"claude_code/pytest/{RUN}", "user/message", AT, "l1", text=f"voici {SECRET}", human=True)
        w.flush()
        assert conn.execute("select count(*) n from walter_logs.events where session_id = %s and text like %s",
                            (f"claude_code/pytest/{RUN}", f"%{SECRET}%")).fetchone()["n"] == 0
    assert purge.verify()["ok"]

    # a restore of older data brings the row back: detected, then removed again
    with connect() as conn:
        conn.execute("set local walter.purge = 'on'")
        cols = [c for c in backup if c != "tsv"]
        conn.execute(f"insert into core.events ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})",
                     [json.dumps(backup[c]) if isinstance(backup[c], dict) else backup[c] for c in cols])
    v = purge.verify()
    assert not v["ok"] and v["present_again"]["event"] == 1
    assert purge.reapply(requested_by="pytest")["status"] == "dry_run"
    r = purge.reapply(requested_by="pytest", execute=True)
    assert r["status"] == "executed" and r["removed"]["events"] == 1
    assert purge.verify()["ok"]
    again = purge.reapply(requested_by="pytest", execute=True)           # idempotent
    assert not again["removed"].get("events")


def test_exposure_never_changes_backups():
    rep = purge.exposure()
    assert rep and all(b["automatic_change"] is False for b in rep)


def test_what_is_built_only_from_purged_knowledge_goes_with_it_and_its_dependents_are_recomputed():
    """20/11: purging a test contact left the facets of his plan's episode (built from the plan alone, no event of
    their own) naming him, and nothing told the episodes and periods that the plan was gone (the publish trigger fires
    on insert and update only). A real item in the same view, with its own sources, is never taken along."""
    run = uuid.uuid4().hex[:10]
    name = f"Pytestine Purgeable {run}"
    ev, real_ev = events.record_events([_ev(f"x{run}", f"{name} propose un café le 12"),
                                        _ev(f"y{run}", f"un vrai souvenir qui cite {name} aussi")])["event_ids"]
    with connect() as conn:
        ent = conn.execute("insert into core.entities (entity_type, canonical_name) values ('person', %s) returning entity_id",
                           (name,)).fetchone()["entity_id"]
        plan = conn.execute("""insert into core.derived_items (kind, content, status, derived_by, source_event_ids,
                                   subject_entity_ids, generation) values ('plan', %s, 'derived', 'pytest', %s::uuid[],
                                   %s::uuid[], 'g1') returning item_id""",
                            (f"Projet : café avec {name}", [ev], [ent])).fetchone()["item_id"]
        facet = conn.execute("""insert into core.derived_items (kind, content, status, derived_by, generation)
                                values ('facet', %s, 'derived', 'pytest', 'g1') returning item_id""",
                             (f"avec {name}",)).fetchone()["item_id"]
        real = conn.execute("""insert into core.derived_items (kind, content, status, derived_by, source_event_ids)
                               values ('fact', %s, 'derived', 'pytest', %s::uuid[]) returning item_id""",
                            (f"un vrai souvenir qui cite {name}", [real_ev])).fetchone()["item_id"]
        view = f"pytest-episode:{run}"
        conn.execute("insert into views.view (view_key, domain, horizon, title, status) values (%s, 'projects', 'long', 't', 'active')", (view,))
        for ref, role in ((plan, "support"), (facet, "facet"), (real, "support")):
            conn.execute("""insert into views.evidence (view_key, ref_kind, ref_id, role, privacy_class, added_by)
                            values (%s, 'derived', %s, %s, 'cloud_allowed', 'pytest')""", (view, str(ref), role))
    dry = purge.purge(reason="pytest", requested_by="pytest", event_ids=[str(ev)])
    assert dry["counts"]["derived"] == 2                       # the plan and its facet, not the real item
    purge.purge(reason="pytest", requested_by="pytest", event_ids=[str(ev)], execute=True)
    with connect() as conn:
        left = {str(r["item_id"]) for r in conn.execute("select item_id from core.derived_items where item_id = any(%s::uuid[])",
                                                         ([plan, facet, real],))}
        pub = conn.execute("""select payload from bus.events where type = 'memory.derived' and subject = %s
                              and payload->>'op' = 'delete'""", (str(plan),)).fetchone()
        conn.execute("delete from core.derived_items where item_id = %s", (real,))
        conn.execute("delete from core.entities where entity_id = %s", (ent,))
    assert left == {str(real)}
    assert pub and pub["payload"]["kind"] == "plan" and pub["payload"]["status"] == "purged" and name not in json.dumps(pub["payload"])


def test_a_period_that_summarised_the_purged_episode_is_masked_too():
    """20/11: the test café's episode was masked, but the December day, week and month views built on it (views.evidence
    ref_kind 'view') kept naming the test contact. A view built on it that never quotes the purged text stays."""
    run = uuid.uuid4().hex[:10]
    name = f"Pytestin Episodique {run}"
    ev = events.record_events([_ev(f"p{run}", f"{name} propose un café le 12")])["event_ids"][0]
    ep, day, month = f"pytest-episode:{run}", f"pytest-day:{run}", f"pytest-month:{run}"
    with connect() as conn:
        ent = conn.execute("insert into core.entities (entity_type, canonical_name) values ('person', %s) returning entity_id",
                           (name,)).fetchone()["entity_id"]
        plan = conn.execute("""insert into core.derived_items (kind, content, status, derived_by, source_event_ids,
                                   subject_entity_ids, generation) values ('plan', %s, 'derived', 'pytest', %s::uuid[],
                                   %s::uuid[], 'g1') returning item_id""",
                            (f"Projet : café avec {name}", [ev], [ent])).fetchone()["item_id"]
        for v in (ep, day, month):
            conn.execute("insert into views.view (view_key, domain, horizon, title, status) values (%s, 'projects', 'long', 't', 'active')", (v,))
        conn.execute("""insert into views.evidence (view_key, ref_kind, ref_id, role, privacy_class, added_by)
                        values (%s, 'derived', %s, 'support', 'cloud_allowed', 'pytest')""", (ep, str(plan)))
        for v, ref in ((day, ep), (month, day)):
            conn.execute("""insert into views.evidence (view_key, ref_kind, ref_id, role, privacy_class, added_by)
                            values (%s, 'view', %s, 'contains', 'cloud_allowed', 'pytest')""", (v, ref))
        conn.execute("insert into views.version (view_key, depth, version, content, builder) values (%s, 'overview', 1, %s, 'pytest')",
                     (ep, f"Café avec {name}"))
        conn.execute("insert into views.version (view_key, depth, version, content, builder) values (%s, 'overview', 1, %s, 'pytest')",
                     (day, f"Le 12 : café proposé par {name}."))
        conn.execute("insert into views.version (view_key, depth, version, content, builder) values (%s, 'overview', 1, %s, 'pytest')",
                     (month, "Décembre : quelques projets, rien de précis."))
    dry = purge.purge(reason="pytest", requested_by="pytest", event_ids=[str(ev)])
    assert dry["counts"]["views_masked"] == 2 and dry["counts"]["view_versions_masked"] == 2
    purge.purge(reason="pytest", requested_by="pytest", event_ids=[str(ev)], execute=True)
    with connect() as conn:
        got = {r["view_key"]: (r["content"], r["stale_since"] is not None) for r in conn.execute(
            "select view_key, content, stale_since from views.version where view_key = any(%s)", ([ep, day, month],))}
        conn.execute("delete from core.entities where entity_id = %s", (ent,))
    assert got[ep] == (purge.MARK, True) and got[day] == (purge.MARK, True)
    assert got[month] == ("Décembre : quelques projets, rien de précis.", False)

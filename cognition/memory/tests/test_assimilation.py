"""Event-driven assimilation (2026-11-03, Monsieur: « event-driven, incrémental, idempotent et traçable »), on the test
database: without a change no model is asked again, and a change recomputes only what depends on it — its burst, its
days, its periods — including late messages, corrections, a crash in the middle and the reconciliation pass."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import assimilation, bus, episodic, events, extract2, flows, generations, llm, periods, processing
from walter_memory.db import connection

Z = flows.tz()
DAY = (datetime.now(timezone.utc) - timedelta(days=3)).astimezone(Z).date()
LATER = datetime.now(timezone.utc) + timedelta(days=1)          # every settle delay and deadline is past


def at(h, m=0, day=None):
    return datetime.combine(day or DAY, datetime.min.time(), Z).replace(hour=h, minute=m).astimezone(timezone.utc)


class Models:
    """Fake chat (plans) and decide (attestation) models that count every call by the tag found in the prompt."""

    def __init__(self, monkeypatch, plans=None):
        self.chat, self.decide, self.plans = [], [], plans or {}
        monkeypatch.setattr(llm, "chat", self._chat)
        monkeypatch.setattr(llm, "decide", self._decide)

    def _chat(self, messages, **kw):
        prompt = messages[0]["content"]
        tag = next((t for t in self.plans if t in prompt), None)
        self.chat.append(tag)
        return {"content": json.dumps({"plans": self.plans.get(tag, [])}), "model": "fake-plans"}

    def _decide(self, state, questions, **kw):
        self.decide.append((state.get("episode", ""), state.get("owner_statement", "")))
        return {"answers": {"verdict": {"choice": "unrelated"}}, "model": "fake-decide"}

    def calls(self, tag):
        return sum(1 for t in self.chat if t == tag)


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    extract2.set_v1_start(datetime.now(timezone.utc) - timedelta(days=30))
    generations.rollback(confirm=True)
    monkeypatch.setattr(assimilation, "engine", lambda: "events")
    monkeypatch.setattr(episodic, "settings", lambda: {"plans_per_run": 20, "attest": True})
    from walter_memory import triage   # the triage of incoming messages has its own tests: never a real model here
    monkeypatch.setattr(triage, "run", lambda *a, **k: {"decided": 0})
    with connection() as conn:   # the test database only: start from the end of the bus, an empty queue
        conn.execute("delete from processing.queue")
        conn.execute("""insert into bus.cursors (consumer, last_tx, last_id)
                        select %s, e.tx, e.id from bus.events e order by e.tx desc, e.id desc limit 1
                        on conflict (consumer) do update set last_tx = excluded.last_tx, last_id = excluded.last_id""",
                     (assimilation.CONSUMER,))


def ev(**kw):
    base = {"source_account": "pytest", "source_id": uuid.uuid4().hex, "privacy_class": "cloud_allowed"}
    return events.record_events([{**base, **kw}])["event_ids"][0]


def msg(thread, t, text, owner=True):
    return ev(event_type="message.sent" if owner else "message.received", source="beeper", thread_id=thread,
              occurred_at=t, content=text, payload={"chat": {"title": f"Chat {thread[:6]}", "network": "whatsapp"}})


def plan(tag, h=20):
    return {"what": f"Dîner {tag}", "start": f"{(DAY + timedelta(days=1)).isoformat()}T{h:02d}:00", "end": None,
            "where": None, "with": [], "agreed": "yes", "msgs": [1], "quote": "on se voit demain"}


def step():
    return assimilation.step(now=LATER)


def derived_events_since(mark):
    with connection() as conn:
        return conn.execute("select count(*) n from bus.events where type = 'memory.derived' and id > %s",
                            (mark,)).fetchone()["n"]


def mine_since(mark, *tags):
    """memory.derived events since `mark` about this test's threads: their bursts, plans, episode facets (the shared
    test database also holds other tests' rows, whose recorded decisions are reset between tests)."""
    with connection() as conn:
        return conn.execute("""select count(*) n from bus.events e join core.derived_items d on d.item_id::text = e.subject
                               where e.id > %s and e.type = 'memory.derived'
                                 and (d.attributes->>'thread' = any(%s)
                                      or exists (select 1 from unnest(%s::text[]) t where d.content like '%%' || t || '%%'))""",
                            (mark, list(tags), list(tags))).fetchone()["n"]


def bus_end():
    with connection() as conn:
        return conn.execute("select coalesce(max(id), 0) m from bus.events").fetchone()["m"]


def bursts(thread):
    with connection() as conn:
        return conn.execute("""select item_id::text, status, attributes from core.derived_items
                               where derived_by = 'flows.conversations' and source_refs->>'ref' like %s
                               order by valid_from""", (f"conv:beeper:{thread}:%",)).fetchall()


def test_without_a_change_no_model_is_asked_again_and_nothing_is_rewritten(monkeypatch):
    a, b = f"A{uuid.uuid4().hex[:8]}", f"B{uuid.uuid4().hex[:8]}"
    m = Models(monkeypatch, plans={a: [plan(a)], b: []})                     # b: a negative answer
    msg(a, at(18), f"{a} on se voit demain 20h ?")
    msg(a, at(18, 5), f"{a} oui parfait", owner=False)
    msg(b, at(9), f"{b} on se voit lundi ?")
    step()
    assert m.calls(a) == 1 and m.calls(b) == 1
    with connection() as conn:
        p = conn.execute("""select status, epistemic from core.derived_items where derived_by = 'episodic.plans'
                            and content like %s""", (f"%Dîner {a}%",)).fetchone()
        ep = conn.execute("select count(*) n from views.view where kind = 'episode' and title like %s and status = 'active'",
                          (f"%Dîner {a}%",)).fetchone()["n"]
    assert p["status"] == "derived" and ep >= 1
    # the shared test database also holds rows written by the former window rebuild: one pass brings them up to date
    flows.conversations(at(0), at(23, 59))
    episodic.build(at(0) - timedelta(days=1), at(0) + timedelta(days=3))
    assimilation.reconcile()
    step()
    asked = len(m.decide)
    mark = bus_end()

    # the same events delivered again (at-least-once), the windows recomputed, the reconciliation pass
    with connection() as conn:
        for t in (a, b):
            for r in conn.execute("select event_id::text, occurred_at from core.events where thread_id = %s", (t,)):
                bus.emit("memory.event", "memory", r["event_id"], {"event_type": "message.sent", "source": "beeper",
                                                                   "thread_id": t, "occurred_at": r["occurred_at"]},
                         conn=conn)
    step()
    flows.conversations(at(0), at(23, 59))
    episodic.build(at(0) - timedelta(days=1), at(0) + timedelta(days=3))
    r = assimilation.reconcile()
    step()
    for x in bursts(a) + bursts(b):                                # asked directly once more: answered from the ledger
        episodic.plan_burst(x["item_id"])
    assert m.calls(a) == 1 and m.calls(b) == 1                     # no plan read twice, the negative one included
    assert len(m.decide) == asked                                  # no attestation judged twice
    assert mine_since(mark, a, b) == 0                             # nothing of theirs rewritten, nothing published
    assert r["missed"] == 0
    with connection() as conn:
        d = conn.execute("""select sum(hits) h from processing.decisions where processor = 'episodic.plans'
                            and input_key = any(%s)""", ([x["item_id"] for x in bursts(a) + bursts(b)],)).fetchone()
    assert d["h"] >= 2                                             # the reuse is traced


def test_a_new_message_recomputes_only_its_burst_its_episode_day_and_its_periods(monkeypatch):
    a, b = f"A{uuid.uuid4().hex[:8]}", f"B{uuid.uuid4().hex[:8]}"
    m = Models(monkeypatch, plans={a: [plan(a)], b: [plan(b, 21)]})
    other_day = DAY - timedelta(days=1)
    msg(a, at(18), f"{a} on se voit demain 20h ?")
    msg(b, at(10, day=other_day), f"{b} demain 21h ça te va ?")
    step()
    assert (m.calls(a), m.calls(b)) == (1, 1)
    with connection() as conn:
        conn.execute("delete from processing.stats")
    mark = bus_end()
    msg(a, at(18, 20), f"{a} je réserve pour 20h", owner=False)        # same burst (20 min later)
    step()
    assert (m.calls(a), m.calls(b)) == (2, 1)                        # only the burst that changed is read again
    with connection() as conn:
        keys = conn.execute("""select type, payload from bus.events where id > %s and type = 'memory.view'""",
                            (mark,)).fetchall()
        burst_b = {x["item_id"] for x in bursts(b)}
        touched = {r["subject"] for r in conn.execute(
            "select subject from bus.events where id > %s and type = 'memory.derived'", (mark,))}
    assert not touched & burst_b                                     # the other thread's burst is untouched
    period_days = {datetime.fromisoformat(str(k["payload"]["starts_at"])).astimezone(Z).date() for k in keys
                   if k["payload"].get("kind") == "period" and k["payload"].get("period") == "day"}
    assert other_day not in period_days and period_days <= {DAY, DAY + timedelta(days=1)}


def test_a_late_message_merges_bursts_and_the_old_ones_and_their_plans_are_retracted(monkeypatch):
    t = f"L{uuid.uuid4().hex[:8]}"
    m = Models(monkeypatch, plans={t: [plan(t)]})
    msg(t, at(10), f"{t} on se voit demain 20h ?")
    msg(t, at(11), f"{t} ok", owner=False)                            # 60 min later: a second burst
    step()
    assert [x["status"] for x in bursts(t)] == ["derived", "derived"]
    msg(t, at(10, 30), f"{t} attends", owner=False)                    # arrives late, bridges the gap
    step()
    live = [x for x in bursts(t) if x["status"] == "derived"]
    assert len(live) == 1 and live[0]["attributes"]["messages"] == 3
    with connection() as conn:
        plans = conn.execute("""select status, attributes->>'burst' burst from core.derived_items
                                where derived_by = 'episodic.plans' and content like %s""", (f"%Dîner {t}%",)).fetchall()
    assert {p["burst"] for p in plans if p["status"] == "derived"} == {live[0]["item_id"]}


def test_attestation_is_judged_once_per_statement_and_again_only_when_it_changes(monkeypatch):
    tag = uuid.uuid4().hex[:6]
    m = Models(monkeypatch)
    with connection() as conn:   # earlier runs' statements of the same shape must not crowd this one out of the top 3
        conn.execute("""update core.derived_items set status = 'superseded'
                        where derived_by = 'l3.extract' and content like 'Monsieur dit que le concert jazz %'""")
    ev(event_type="calendar.event", source="calendar", occurred_at=at(20),
       content=f"Concert Jazz {tag}", payload={"event_id": f"cal-{tag}", "calendar_id": "owner@example.invalid",
                                               "start": {"dateTime": at(20).astimezone(Z).isoformat()},
                                               "end": {"dateTime": at(22).astimezone(Z).isoformat()}, "attendees": []})
    with connection() as conn:
        sid = conn.execute("""insert into core.derived_items (kind, content, status, derived_by, source_refs, valid_from,
                                  privacy_class, generation, epistemic, stage, scope)
                              values ('fact', %s, 'derived', 'l3.extract', %s, %s, 'cloud_allowed', 'g1', 'stated_owner',
                                      'stated', 'durable') returning item_id::text""",
                           (f"Monsieur dit que le concert jazz {tag} était super", json.dumps({"ref": f"t-{tag}"}),
                            at(23))).fetchone()["item_id"]
    mine = lambda: [p for p in m.decide if tag in p[0] and tag in p[1]]      # noqa: E731 — this episode, this statement
    step()
    assert len(mine()) == 1
    episodic.build_day(DAY)
    step()
    assert len(mine()) == 1                                            # same episode, same statement: reused
    with connection() as conn:
        conn.execute("update core.derived_items set content = content || ' (et bondé)' where item_id = %s", (sid,))
    step()
    assert len(mine()) == 2                                            # the statement changed: judged again, once


def test_a_cancelled_appointment_retires_its_episode_and_updates_its_day(monkeypatch):
    tag = uuid.uuid4().hex[:6]
    Models(monkeypatch)
    payload = {"event_id": f"cal-{tag}", "calendar_id": "owner@example.invalid",
               "start": {"dateTime": at(15).astimezone(Z).isoformat()},
               "end": {"dateTime": at(16).astimezone(Z).isoformat()}, "attendees": []}
    ev(event_type="calendar.event", source="calendar", occurred_at=at(15), content=f"Dentiste {tag}", payload=payload)
    step()
    with connection() as conn:
        live = conn.execute("""select view_key from views.view where kind = 'episode' and status = 'active'
                               and title like %s""", (f"%Dentiste {tag}%",)).fetchall()
    assert live
    ev(event_type="calendar.event", source="calendar", occurred_at=at(15), content=f"Dentiste {tag}",
       payload={**payload, "status": "cancelled"})
    step()
    with connection() as conn:
        st = {r["status"] for r in conn.execute("select status from views.view where view_key = any(%s)",
                                                 ([r["view_key"] for r in live],))}
        app = conn.execute("""select status from core.derived_items where derived_by = 'flows.appointments'
                              and source_refs->>'ref' = %s""", (f"cal:cal-{tag}",)).fetchone()
        day = conn.execute("""select content from views.version where view_key = %s and depth = 'details'
                              order by version desc limit 1""", (f"period:day:{DAY.isoformat()}",)).fetchone()
    assert st == {"retired"} and app["status"] == "retracted"
    assert f"Dentiste {tag}" not in (day or {}).get("content", "")


def test_a_crash_keeps_the_work_and_it_resumes(monkeypatch):
    t = f"C{uuid.uuid4().hex[:8]}"
    Models(monkeypatch, plans={t: []})
    real = flows.conversations
    boom = {"n": 1}

    def flaky(*a, **kw):
        if boom["n"]:
            boom["n"] -= 1
            raise RuntimeError("database went away")
        return real(*a, **kw)

    monkeypatch.setattr(flows, "conversations", flaky)
    msg(t, at(12), f"{t} salut")
    assimilation.step(now=LATER, rounds=1)
    with connection() as conn:
        q = conn.execute("""select attempts, last_error from processing.queue where processor = 'flows.conversations'
                            and key like %s""", (f"%{t}",)).fetchone()
    assert q and q["attempts"] == 1 and "went away" in q["last_error"] and not bursts(t)
    step()
    with connection() as conn:
        q = conn.execute("select 1 from processing.queue where processor = 'flows.conversations' and key like %s",
                         (f"%{t}",)).fetchone()
    assert q is None and len(bursts(t)) == 1


def test_a_mark_during_processing_is_not_lost():
    with connection() as conn:
        processing.mark(conn, "periods.day", "2001-01-01", reason="a")
    row = processing.due("periods.day", LATER)[0]
    with connection() as conn:          # a new event arrives while the key is being processed
        processing.mark(conn, "periods.day", "2001-01-01", reason="b")
    assert processing.done(row) is False
    assert [r["key"] for r in processing.due("periods.day", LATER)] == ["2001-01-01"]


def test_a_stale_period_with_the_same_inputs_gets_no_new_version():
    periods.build("day", DAY)
    key = f"period:day:{DAY.isoformat()}"
    with connection() as conn:
        n0 = conn.execute("select count(*) n from views.version where view_key = %s", (key,)).fetchone()["n"]
        conn.execute("""update views.version v set stale_since = now() where v.view_key = %s
                        and v.version = (select max(version) from views.version x where x.view_key = v.view_key
                                         and x.depth = v.depth)""", (key,))     # as invalidate() does
    r = periods.build("day", DAY)
    with connection() as conn:
        n1 = conn.execute("select count(*) n from views.version where view_key = %s", (key,)).fetchone()["n"]
        stale = conn.execute("""select count(*) n from views.version v where v.view_key = %s and stale_since is not null
                                and v.version = (select max(version) from views.version x where x.view_key = v.view_key
                                                 and x.depth = v.depth)""", (key,)).fetchone()["n"]
    assert not r["cloud"]["rebuilt"] and n1 == n0 and stale == 0


def test_unchanged_flows_publish_nothing():
    t = f"F{uuid.uuid4().hex[:8]}"
    msg(t, at(8), f"{t} bonjour")
    flows.conversations(at(0), at(23, 59))
    flows.work_sessions(at(0), at(23, 59))
    flows.appointments()
    mark = bus_end()
    flows.conversations(at(0), at(23, 59))
    flows.work_sessions(at(0), at(23, 59))
    flows.appointments()
    assert derived_events_since(mark) == 0


def test_a_new_message_is_searchable_after_one_step_without_the_index_timer():
    t = f"I{uuid.uuid4().hex[:8]}"
    e = msg(t, at(9), f"{t} le mot de passe du wifi est sur le frigo")
    step()
    with connection() as conn:
        assert conn.execute("select 1 from search.chunks where kind = 'event' and ref_id = %s", (e,)).fetchone()


def test_a_long_stay_cut_by_the_window_edge_is_one_visit_from_its_true_start():
    n = int(uuid.uuid4().hex[:4], 16)
    lat = 13.70 + n * 1e-6                                                   # a place of its own (distinct at 6 decimals)
    t0 = at(1, day=DAY - timedelta(days=30 + n % 300))                       # a night no other test or run uses
    for k in range(60):                                                      # 10 h at the same place
        ev(event_type="location.sample", source="overland", occurred_at=t0 + timedelta(minutes=10 * k),
           privacy_class="local_only", payload={"lat": lat, "lng": 100.9, "accuracy_m": 10, "raw": {"properties": {}}})
    for edge in (4, 5, 6):                                                   # the window slides over the stay
        flows.visits(t0 + timedelta(hours=edge), t0 + timedelta(hours=12))
    with connection() as conn:
        rows = conn.execute("""select valid_from from core.derived_items where derived_by = 'flows.visits'
                               and status = 'derived' and (attributes->>'lat')::float = %s""", (round(lat, 6),)).fetchall()
    assert [r["valid_from"] for r in rows] == [t0]


def test_a_proposed_name_match_is_neither_a_participant_nor_a_second_copy_of_the_message():
    """2026-11-09 (g1 audit): a sender with a confirmed entity AND a proposed name match (a namesake) was joined to both:
    each of its messages counted twice and the namesake listed as a participant (536 / 1 744 bursts in production)."""
    th = "fanout-" + uuid.uuid4().hex[:8]
    with connection() as conn:
        ident = events.upsert_identity(conn, "beeper", {"external_id": th + "-paul", "display_name": "Paul"})
        real, namesake = [conn.execute("""insert into core.entities (entity_type, canonical_name) values ('person', %s)
                                          returning entity_id::text""", (n,)).fetchone()["entity_id"]
                          for n in (f"Paul Vrai {th}", f"Paul Homonyme {th}")]
        conn.execute("""insert into core.identity_links (identity_id, entity_id, status, confidence, method)
                        values (%s, %s, 'confirmed', 1.0, 'test'), (%s, %s, 'proposed', 0.6, 'test')""",
                     (ident, real, ident, namesake))
    msg(th, at(10), "Salut, on se voit demain ?")
    ev(event_type="message.received", source="beeper", thread_id=th, occurred_at=at(10, 5), content="Oui !",
       actor_identity_id=ident, payload={"chat": {"title": f"Chat {th[:6]}", "network": "whatsapp"}})
    flows.conversations(at(0), at(23, 59))
    (b,) = [x for x in bursts(th) if x["status"] == "derived"]
    assert b["attributes"]["messages"] == 2 and b["attributes"]["participants"] == [real]
    with connection() as conn:
        assert [r["who"] for r in episodic._burst_messages(conn.execute(
            "select source_event_ids from core.derived_items where item_id = %s", (b["item_id"],)).fetchone())] \
            == [None, f"Paul Vrai {th}"]


def test_the_index_follows_a_changed_burst_and_drops_a_retracted_one():
    """2026-11-09 (g1 audit): index_pending only indexes items without chunks, so a burst that grew kept its first text
    (unfindable as it now reads) and a retracted one stayed indexed. An update now re-indexes the item (event-driven);
    the reconciliation finds whatever is still stale."""
    from walter_memory import search
    th = "reidx-" + uuid.uuid4().hex[:8]
    msg(th, at(9), f"Premier message {th}")
    step()
    (b,) = [x for x in bursts(th) if x["status"] == "derived"]
    def text():
        with connection() as conn:
            return [r["text"] for r in conn.execute(
                "select text from search.chunks where kind = 'derived' and ref_id = %s", (b["item_id"],))]
    assert text() and "1 messages" in text()[0]
    msg(th, at(9, 10), f"Second message {th}")
    step()
    (b2,) = [x for x in bursts(th) if x["status"] == "derived"]
    assert b2["item_id"] == b["item_id"] and b2["attributes"]["messages"] == 2
    assert len(text()) == 1 and "2 messages" in text()[0]
    assert b["item_id"] not in search.stale_derived()
    with connection() as conn:          # retracted behind the bus's back: the reconciliation's sweep catches it
        conn.execute("set local session_replication_role = replica")
        conn.execute("update core.derived_items set status = 'retracted' where item_id = %s", (b["item_id"],))
    assert b["item_id"] in search.stale_derived()
    assert search.reindex_derived([b["item_id"]]) == {"unchanged": 0, "reindexed": 0, "removed": 1, "skipped": 0}
    assert text() == [] and search.reindex_derived([b["item_id"]])["unchanged"] == 1

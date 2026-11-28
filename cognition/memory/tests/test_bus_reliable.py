"""Reliable bus (migration 023): gap-free cursors under concurrent transactions, outbox trigger on core.events,
retries with backoff, dead letters and replay, crash recovery. Test database only (conftest)."""
import random
import threading
import time
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from walter_memory import bus, events
from walter_memory.db import DSN, connection

RUN = uuid.uuid4().hex[:8]


def _tx_insert(conn, type_, subject):
    return conn.execute("insert into bus.events (type, source, subject) values (%s, 'pytest', %s) returning id",
                        (type_, subject)).fetchone()[0]


def test_a_late_commit_with_a_lower_id_is_never_skipped():
    t = f"pytest.gap.{RUN}"
    c = bus.Consumer(f"pytest-gap-{RUN}", [t])
    c.drain(lambda e: None)
    a = psycopg.connect(DSN); b = psycopg.connect(DSN)
    try:
        id_a = _tx_insert(a, t, "A")             # A takes the lower id and stays open
        id_b = _tx_insert(b, t, "B"); b.commit()  # B commits first with the higher id
        assert id_a < id_b
        seen = []
        c.drain(lambda e: seen.append(e["subject"]))
        assert seen == []                         # B is held: A could still commit below it
        assert bus.lag(c.name, [t])["held"] >= 1
        a.commit()
        c.drain(lambda e: seen.append(e["subject"]))
        assert sorted(seen) == ["A", "B"]          # the old id cursor would have lost A
    finally:
        a.close(); b.close()


def test_no_loss_under_many_concurrent_writers_and_a_live_consumer():
    t = f"pytest.conc.{RUN}"
    c = bus.Consumer(f"pytest-conc-{RUN}", [t], batch=7)
    c.drain(lambda e: None)
    written, seen, stop = set(), [], threading.Event()
    lock = threading.Lock()

    def writer(k):
        rnd = random.Random(k)
        with psycopg.connect(DSN) as conn:
            for i in range(25):
                subj = f"{k}-{i}"
                _tx_insert(conn, t, subj)
                time.sleep(rnd.random() * 0.02)       # commits land out of id order
                if rnd.random() < 0.15:
                    conn.rollback()                    # aborted transactions must not be delivered
                else:
                    conn.commit()
                    with lock:
                        written.add(subj)

    def consumer():
        while not stop.is_set():
            c.drain(lambda e: seen.append(e["subject"]))
            time.sleep(0.005)
    ct = threading.Thread(target=consumer); ct.start()
    ws = [threading.Thread(target=writer, args=(k,)) for k in range(8)]
    for w in ws:
        w.start()
    for w in ws:
        w.join()
    time.sleep(0.2); stop.set(); ct.join()
    c.drain(lambda e: seen.append(e["subject"]))
    assert set(seen) == written and len(seen) == len(written)    # nothing lost, nothing delivered twice


def _event(src_id, **kw):
    return {"event_type": "note.recorded", "source": "walter", "source_account": "pytest", "source_id": src_id,
            "occurred_at": datetime.now(timezone.utc), "content": f"pytest note {src_id}",
            "privacy_class": "cloud_allowed", **kw}


def test_every_new_canonical_event_is_published_in_its_transaction():
    sid = f"pytest-pub-{RUN}"
    res = events.record_events([_event(sid)])
    eid = res["event_ids"][0]
    with connection() as conn:
        rows = conn.execute("select type, payload from bus.events where subject = %s", (eid,)).fetchall()
    assert len(rows) == 1 and rows[0]["type"] == "memory.event"
    assert rows[0]["payload"]["event_type"] == "note.recorded" and rows[0]["payload"]["privacy_class"] == "cloud_allowed"
    assert events.record_events([_event(sid)])["inserted"] == 0          # duplicate: no second publication
    with connection() as conn:
        assert conn.execute("select count(*) n from bus.events where subject = %s", (eid,)).fetchone()["n"] == 1
    # rolled back insert: neither the event nor its publication exists
    with pytest.raises(RuntimeError):
        with connection() as conn:
            r = events.record_events([_event(sid + "-rb")], conn=conn)
            rid = r["event_ids"][0]
            raise RuntimeError("abort")
    with connection() as conn:
        assert conn.execute("select count(*) n from bus.events where subject = %s", (rid,)).fetchone()["n"] == 0


def test_transactional_emit_exists_only_if_the_caller_commits():
    t = f"pytest.txemit.{RUN}"
    with pytest.raises(RuntimeError):
        with connection() as conn:
            bus.emit(t, "pytest", "x", conn=conn)
            raise RuntimeError("abort")
    with connection() as conn:
        bus.emit(t, "pytest", "y", conn=conn)
        assert conn.execute("select count(*) n from bus.events where type = %s", (t,)).fetchone()["n"] == 1
    with connection() as conn:
        assert [r["subject"] for r in conn.execute("select subject from bus.events where type = %s", (t,))] == ["y"]


def _due_now(name):
    with connection() as conn:
        conn.execute("update bus.dead set next_at = now() - interval '1 second' where consumer = %s", (name,))


def test_failure_is_retried_with_backoff_then_resolved():
    t = f"pytest.retry.{RUN}"
    c = bus.Consumer(f"pytest-retry-{RUN}", [t])
    bus.emit(t, "pytest", "flaky")
    calls = []

    def handler(e):
        calls.append(e["subject"])
        if len(calls) < 3:
            raise ConnectionError("transient")
    c.drain(handler)
    with connection() as conn:
        d = conn.execute("select status, attempts, next_at > now() as later from bus.dead where consumer = %s",
                         (c.name,)).fetchone()
    assert d["status"] == "retrying" and d["attempts"] == 1 and d["later"]
    assert c.retry_due(handler) == {"retried": 0, "resolved": 0, "failed": 0}   # not due yet: backoff
    _due_now(c.name); assert c.retry_due(handler)["failed"] == 1
    _due_now(c.name); assert c.retry_due(handler)["resolved"] == 1
    with connection() as conn:
        assert conn.execute("select status from bus.dead where consumer = %s", (c.name,)).fetchone()["status"] == "resolved"


def test_poison_event_becomes_dead_then_replay_brings_it_back():
    t = f"pytest.poison.{RUN}"
    c = bus.Consumer(f"pytest-poison-{RUN}", [t], max_attempts=3)
    bus.emit(t, "pytest", "poison")
    fixed = {"ok": False}

    def handler(e):
        if not fixed["ok"]:
            raise ValueError("bad payload")
    c.drain(handler)
    for _ in range(3):
        _due_now(c.name); c.retry_due(handler)
    assert [d["status"] for d in bus.dead(c.name)] == ["dead"]
    assert bus.lag(c.name, [t])["dead"] == 1
    fixed["ok"] = True                       # the handler is repaired
    assert bus.replay(c.name) == 1
    assert c.retry_due(handler)["resolved"] == 1


def test_a_crash_mid_batch_redelivers_from_the_cursor():
    t = f"pytest.crash.{RUN}"
    c = bus.Consumer(f"pytest-crash-{RUN}", [t])
    for i in range(5):
        bus.emit(t, "pytest", str(i))
    seen = []

    def crashing(e):
        if e["subject"] == "2":
            raise SystemExit("process killed")    # not an Exception: nothing is recorded, the cursor stays
        seen.append(e["subject"])
    with pytest.raises(SystemExit):
        c.drain(crashing)
    again = bus.Consumer(c.name, [t])            # restarted process
    again.drain(lambda e: seen.append(e["subject"]))
    assert seen == ["0", "1", "2", "3", "4"]


def test_old_rows_keep_their_order_with_tx_zero():
    t = f"pytest.legacy.{RUN}"
    with connection() as conn:
        conn.execute("insert into bus.events (type, source, subject, tx) values (%s, 'pytest', 'old', '0')", (t,))
    c = bus.Consumer(f"pytest-legacy-{RUN}", [t])
    seen = []
    bus.emit(t, "pytest", "new")
    c.drain(lambda e: seen.append(e["subject"]))
    assert seen == ["old", "new"]

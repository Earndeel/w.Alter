"""Walter bus: emit → wake-up → consume, cursor catch-up, dedupe, dead letters, batches. Uses type 'pytest.*' events
and consumer names 'pytest-*', removed at the end. Run: cd /opt/walter-memory && venv/bin/python -m pytest -q tests/"""
import threading
import time
import uuid

import pytest

from walter_memory import bus
from walter_memory.db import connection

RUN = uuid.uuid4().hex[:8]
T = f"pytest.{RUN}"


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    with connection() as c:
        c.execute("delete from bus.dead where consumer like 'pytest-%'")
        c.execute("delete from bus.cursors where consumer like 'pytest-%'")
        c.execute("delete from bus.events where type like 'pytest.%'")


def test_emit_dedupes_and_never_raises(monkeypatch):
    assert bus.emit(T, "pytest", "a", {"x": 1}, dedupe_key=f"{RUN}-k") is not None
    assert bus.emit(T, "pytest", "a", {"x": 1}, dedupe_key=f"{RUN}-k") is None
    monkeypatch.setattr(bus, "DSN", "host=127.0.0.1 port=1 connect_timeout=1")
    assert bus.emit(T, "pytest", "down") is None  # fail-open: a hook never breaks because the bus is down


def test_consumer_catches_up_then_is_woken_live():
    c = bus.Consumer(f"pytest-live-{RUN}", [T])
    c.drain(lambda e: None)
    bus.emit(T, "pytest", "before")             # emitted while the consumer is not running → catch-up
    got = []
    threading.Thread(target=c.run, args=(lambda e: got.append(e["subject"]),), daemon=True).start()
    time.sleep(1.5)
    bus.emit(T, "pytest", "live")
    for _ in range(40):
        if "live" in got:
            break
        time.sleep(0.05)
    assert got == ["before", "live"]


def test_failing_event_goes_to_dead_and_the_stream_moves_on():
    c = bus.Consumer(f"pytest-dead-{RUN}", [T + ".d"])
    bad, good = bus.emit(T + ".d", "pytest", "bad"), bus.emit(T + ".d", "pytest", "good")
    seen = []

    def handler(e):
        if e["subject"] == "bad":
            raise ValueError("boom")
        seen.append(e["subject"])
    assert c.drain(handler) == 2 and seen == ["good"]
    assert bus.lag(c.name, c.types) == {"pending": 0, "oldest_s": 0, "dead_24h": 1}
    with connection() as conn:
        assert conn.execute("select event_id from bus.dead where consumer = %s", (c.name,)).fetchone()["event_id"] == bad
    assert good > bad


def test_batch_mode_hands_a_burst_over_at_once():
    c = bus.Consumer(f"pytest-batch-{RUN}", [T + ".b"], batch=2)  # page size 2: the batch must still hold all 5
    for i in range(5):
        bus.emit(T + ".b", "pytest", str(i))
    batches = []
    assert c.drain_batch(lambda evs: batches.append([e["subject"] for e in evs])) == 5
    assert batches == [["0", "1", "2", "3", "4"]] and c.drain_batch(lambda evs: batches.append(evs)) == 0

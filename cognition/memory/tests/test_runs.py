"""Walter Run Plane (P0). Writes runs whose origin.runtime is 'pytest' and removes them (and their bus events) at the end."""
import pytest

from walter_memory import runs
from walter_memory.db import connect


@pytest.fixture(autouse=True)
def cleanup():
    yield
    with connect() as c:
        ids = [str(r["run_id"]) for r in c.execute("select run_id from runs.runs where origin->>'runtime' = 'pytest'")]
        if ids:
            c.execute("delete from bus.events where source = 'runs' and subject = any(%s)", (ids,))
            c.execute("delete from runs.links where run_id::text = any(%s)", (ids,))
            c.execute("delete from runs.tasks where run_id::text = any(%s)", (ids,))
            c.execute("delete from runs.runs where run_id::text = any(%s)", (ids,))


def origin(sid="pytest/s1"):
    return {"channel": "owner", "runtime": "pytest", "session_id": sid}


def test_uuid7_is_time_ordered_and_versioned():
    a, b = runs.new_id(), runs.new_id()
    assert a[14] == "7" and a[:8] <= b[:8]


def test_start_is_idempotent_on_dedupe_key_and_emits_once():
    r1 = runs.start(origin=origin(), goal="hello", dedupe_key="pytest/s1/1")
    r2 = runs.start(origin=origin(), goal="hello", dedupe_key="pytest/s1/1")
    assert r1 == r2
    with connect() as c:
        n = c.execute("select count(*) n from bus.events where type = 'run.created' and subject = %s", (r1,)).fetchone()["n"]
    assert n == 1


def test_end_once_and_end_open_by_session():
    r = runs.start(origin=origin("pytest/s2"), goal="x")
    assert runs.end_open("pytest/s2") == r
    runs.end(r, "failed")                       # already closed: unchanged
    shown = runs.show(r)
    assert shown["run"]["status"] == "ended" and shown["links"][0]["ref"] == "pytest/s2"


def test_local_only_goal_is_not_stored_and_goal_is_masked():
    r = runs.start(origin=origin(), goal="secret stuff", privacy_class="local_only")
    assert runs.show(r)["run"]["goal"] is None


def test_task_lifecycle_and_routing():
    r = runs.start(origin=origin(), goal="parent")
    t = runs.task_start(r, kind="walter_run", goal="child", spec={"toolsets": ["walter-web"]}, session_id="walter-router/x")
    runs.routing(r, {"task": "research", "model": "m", "applied": True}, task_id=t)
    runs.task_end(t, result={"ok": True})
    shown = runs.show(r)
    assert shown["tasks"][0]["status"] == "ended" and shown["tasks"][0]["routing"]["model"] == "m"
    assert {"session"} <= {l["kind"] for l in shown["links"]}


def test_safe_never_raises_and_respects_switch(monkeypatch):
    assert runs.safe(lambda: 1 / 0) is None
    monkeypatch.setenv("WALTER_RUNS", "off")
    assert runs.safe(lambda: 42) is None


def test_trace_writes_a_masked_walter_logs_session_from_iso_times():
    r = runs.start(origin=origin(), goal="parent")
    t = runs.task_start(r, kind="walter_run", session_id="pytest-trace/1")
    evs = [{"type": "user/message", "text": "goal", "at": "2026-10-27T18:40:45+00:00"},
           {"type": "tool/call", "tool": "walter_browse", "call_id": "c0", "text": "{\"query\": \"q\"}", "at": "2026-10-27T18:40:46+00:00"},
           {"type": "tool/result", "tool": "walter_browse", "call_id": "c0", "text": "{}", "at": "2026-10-27T18:40:47+00:00"},
           {"type": "assistant/message", "text": "done", "at": "2026-10-27T18:40:48+00:00"}]
    try:
        assert runs.trace("pytest-trace/1", evs, runtime="walter-router", native_id=t) == 4
        assert runs.trace("pytest-trace/1", evs, runtime="walter-router", native_id=t) == 0   # idempotent
        with connect() as c:
            tools = [x["tool"] for x in c.execute("select tool from walter_logs.events where session_id = 'pytest-trace/1' and type = 'tool/call'")]
        assert tools == ["walter_browse"]
    finally:
        with connect() as c:
            c.execute("delete from walter_logs.events where session_id = 'pytest-trace/1'")
            c.execute("delete from walter_logs.sessions where session_id = 'pytest-trace/1'")

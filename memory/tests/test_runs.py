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


def test_repair_goal_keeps_the_original_and_emits():
    notice = 'The approval policy changed from "ask" to "never" (changed by the user).'
    r = runs.start(origin=origin("pytest/s9"), goal=notice + "test")
    out = runs.repair_goal(r, "test", "dsh runtime notice glued to the owner prompt")
    run = runs.show(r)["run"]
    assert out["goal"] == "test" and run["goal"] == "test" and "episode" not in out
    assert run["origin"]["goal_repairs"][0]["original"] == notice + "test"
    assert runs.repair_goal(r, "test", "again") == {"run_id": r, "unchanged": True}
    with connect() as c:
        assert c.execute("select count(*) n from bus.events where type = 'run.goal_repaired' and subject = %s",
                         (r,)).fetchone()["n"] == 1


def test_preflight_request_is_kept_next_to_the_observed_route():
    """Lot 2 (2026-11-07): the preflight's request to the Router lives in routing.requested; the gateway's observed
    route does not erase it, and unknown keys never enter it."""
    import json, subprocess
    r = runs.start(origin=origin("pytest/s10"), goal="test")
    runs.routing(r, {"applied": False, "configured": True})
    runs.update(r, level="L0", act="new", requested={"task": "general", "level": "L1", "fast_path": "trivial",
                                                     "answer": "12", "message_sha": "ab", "prompt": "never kept"})
    runs.routing(r, {"applied": True, "provider": "codex", "model": "m"})
    routing = runs.show(r)["run"]["routing"]
    assert routing["applied"] is True and routing["provider"] == "codex" and "configured" not in routing
    assert routing["requested"] == {"task": "general", "level": "L1", "fast_path": "trivial", "answer": "12",
                                    "message_sha": "ab"}
    out = json.loads(subprocess.run(["walter-memory", "runs", "find", r, "--open-only"], capture_output=True,
                                    text=True, timeout=30).stdout)
    assert out["requested"]["task"] == "general" and out["status"] == "open"
    plain = runs.start(origin=origin("pytest/s11"), goal="x")
    runs.routing(plain, {"applied": False})
    assert "requested" not in runs.show(plain)["run"]["routing"]

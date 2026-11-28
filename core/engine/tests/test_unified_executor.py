"""Lot 3e step 2 (2026-11-26): one executor whatever the door — the model's direct call, the generic `walter_call`,
Python's `await tools.x()`. Same policy decision, one execution, one journal entry, arguments checked against the
tool's own schema, a shared resource locked across tools, sessions and agents, and an effectful call whose answer
is lost said to be of unknown outcome (never retried). Offline: witness tools, no network, no model."""
import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walter_engine import config  # noqa: E402
from walter_engine.tools import Result, Tool, obj  # noqa: E402

W = "mcp__walter__"


def _settings(tmp_path):
    return config.Settings(state=tmp_path / "state", trusted_hosts=["portal.example"],
                           login_url_file=tmp_path / "login-url", web_cookie_days=365)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    from walter_engine import engine as E
    eng = E.Engine(_settings(tmp_path))
    judged = []

    async def judge(*, tool, args, door, depth, principal):
        judged.append(tool)
        return {"decision": "allow", "rule": "test"}
    monkeypatch.setattr(eng.policy, "judge", judge)

    async def no_state(*a, **k):        # no event towards Context's services from a test
        return None
    monkeypatch.setattr(eng, "state_event", no_state)
    eng.judged = judged
    yield eng
    asyncio.run(eng.doors.close())
    asyncio.run(eng.llm.close())


def _agent(engine, sid=None):
    return engine.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"}, **({"sid": sid} if sid else {}))


def _witness(engine, *, effects=("record",), concurrency="parallel", name="witness", run=None):
    runs = []

    async def default(args, ex):
        runs.append(dict(args))
        return Result("done", value={"ok": True})
    engine.registry.add(Tool(W + name, "A witness tool.", obj({"x": {"type": "string"}}, ["x"]), run or default,
                             parallel=concurrency == "parallel", source="mcp:walter", hidden=True,
                             spec={"effects": list(effects), "concurrency": concurrency}))
    return runs


def test_three_doors_one_decision_one_execution_one_journal_entry(engine):
    runs = _witness(engine)
    a = _agent(engine)
    direct = asyncio.run(engine.execute_tool(a, W + "witness", {"x": "1"}, via="model", journal_call=False))
    generic = asyncio.run(engine.execute_tool(a, W + "walter_call", {"tool": "witness", "arguments": {"x": "2"}},
                                              via="model", journal_call=False))
    py = asyncio.run(engine.execute_tool(a, W + "walter_call", {"tool": "witness", "arguments": {"x": "3"}},
                                         via="python", journal_call=True))
    assert not (direct.is_error or generic.is_error or py.is_error)
    assert engine.judged == [W + "witness"] * 3                       # the policy sees the tool, not the door
    assert [r["x"] for r in runs] == ["1", "2", "3"]                  # each call ran exactly once
    assert generic.meta["door"] == "walter_call" and generic.meta["resolved"] == W + "witness"
    nested = [e["data"] for e in a.session.events if e["type"] == "tool/call"]
    assert len(nested) == 1 and nested[0]["name"] == W + "witness" and nested[0]["door"] == "walter_call"


def test_the_generic_door_opens_neither_itself_nor_python(engine):
    a = _agent(engine)
    for target in ("walter_call", "python", "mcp__walter__walter_call"):
        res = asyncio.run(engine.execute_tool(a, W + "walter_call", {"tool": target}, via="model", journal_call=False))
        assert res.is_error and json.loads(res.content)["error"] == "invalid_request"
    assert engine.judged == []


def test_an_unknown_tool_behind_the_generic_door_suggests_close_names(engine):
    _witness(engine)
    res = asyncio.run(engine.execute_tool(_agent(engine), W + "walter_call", {"tool": "witnes", "arguments": {"x": "1"}},
                                          via="model", journal_call=False))
    err = json.loads(res.content)
    assert res.is_error and err["error"] == "not_found" and "witness" in err["candidates"]


def test_unknown_and_missing_arguments_are_refused_with_the_schema(engine):
    runs = _witness(engine)
    a = _agent(engine)
    res = asyncio.run(engine.execute_tool(a, W + "witness", {"x": "1", "ref": "s#3"}, via="python", journal_call=True))
    err = json.loads(res.content)
    assert res.is_error and err["error"] == "invalid_request" and "ref" in err["message"]
    assert err["parameters"] == {"x": {"type": "string"}} and err["required"] == ["x"]
    res = asyncio.run(engine.execute_tool(a, W + "walter_call", {"tool": "witness", "arguments": {}}, via="model",
                                          journal_call=False))
    assert res.is_error and "missing" in json.loads(res.content)["message"]
    assert runs == [] and engine.judged == []                          # nothing ran, nothing was even judged


def _slow(engine, name, log, *, resource="file", key="file_path"):
    async def run(args, ex):
        log.append(("start", args[key], time.monotonic()))
        await asyncio.sleep(0.05)
        log.append(("end", args[key], time.monotonic()))
        return Result("ok")
    engine.registry.add(Tool(name, "slow", obj({key: {"type": "string"}}, [key]), run, source="engine",
                             spec={"effects": ["local_write"], "concurrency": {"resource": resource, "key": key}}))


def _overlap(log):
    depth, most = 0, 0
    for kind, _, _ in sorted(log, key=lambda r: (r[2], r[0] == "start")):
        depth += 1 if kind == "start" else -1
        most = max(most, depth)
    return most


def test_one_resource_is_held_by_one_call_whatever_the_tool_session_or_agent(engine, tmp_path):
    log = []
    _slow(engine, "slow_write", log)
    _slow(engine, "slow_edit", log)
    a, b = _agent(engine), _agent(engine)
    f = str(tmp_path / "same.txt")

    async def go():
        await asyncio.gather(engine.execute_tool(a, "slow_write", {"file_path": f}, via="python", journal_call=True),
                             engine.execute_tool(b, "slow_edit", {"file_path": f}, via="python", journal_call=True),
                             engine.execute_tool(a, "slow_edit", {"file_path": f + "/../same.txt"}, via="model",
                                                 journal_call=False))
    (tmp_path / "same.txt").write_text("")
    asyncio.run(go())
    assert _overlap(log) == 1                                     # never two at once on one file (any path naming it)
    log.clear()

    async def apart():
        await asyncio.gather(*(engine.execute_tool(a, "slow_write", {"file_path": str(tmp_path / f"f{i}")},
                                                   via="python", journal_call=True) for i in range(3)))
    asyncio.run(apart())
    assert _overlap(log) == 3                                     # different files: in parallel


def test_an_effectful_call_interrupted_while_running_has_an_unknown_outcome(engine):
    started = []

    async def hang(args, ex):
        started.append(1)
        await asyncio.sleep(30)
    _witness(engine, run=hang)
    _witness(engine, name="looker", effects=("none",), run=hang)
    a = _agent(engine)

    async def interrupted(tool):
        task = asyncio.ensure_future(engine.execute_tool(a, W + tool, {"x": "1"}, via="python",
                                                         cancel=asyncio.Event(), journal_call=True))
        n = len(started)
        while len(started) == n:
            await asyncio.sleep(0.005)
        task.cancel()
        return await task

    async def both():
        return await interrupted("witness"), await interrupted("looker")
    effectful, read = asyncio.run(both())
    err = json.loads(effectful.content)
    assert effectful.is_error and err["error"] == "outcome_unknown" and effectful.meta["outcome"] == "unknown"
    assert "check whether it took effect" in err["message"]          # idempotency none: never retried blindly
    assert read.is_error and read.content == "[interrupted]"         # a read lost nothing


def test_a_call_interrupted_while_waiting_for_its_resource_never_ran(engine, tmp_path):
    log = []
    _slow(engine, "slow_write", log)
    a = _agent(engine)
    f = str(tmp_path / "x")

    async def go():
        first = asyncio.ensure_future(engine.execute_tool(a, "slow_write", {"file_path": f}, via="python",
                                                          journal_call=True))
        await asyncio.sleep(0.01)
        cancel = asyncio.Event()
        second = asyncio.ensure_future(engine.execute_tool(a, "slow_write", {"file_path": f}, via="python",
                                                           cancel=cancel, journal_call=True))
        await asyncio.sleep(0.01)
        second.cancel()
        return await first, await second
    first, second = asyncio.run(go())
    assert not first.is_error and second.content == "[interrupted before it started]"
    assert [k for k, *_ in log] == ["start", "end"]                  # the waiting call never started


def test_the_engine_declares_every_native_tool(engine):
    from walter_engine.tools import NATIVE_SPECS, agents, builtin
    builtin.register(engine.registry)
    agents.register(engine.registry)
    engine.registry.add(engine.python.tool())
    natives = {n for n, t in engine.registry.tools.items() if t.source == "engine"}
    assert natives <= set(NATIVE_SPECS) and all(engine.registry.tools[n].spec for n in natives)
    from walter_engine.tools import capabilities
    for n in natives:
        capabilities().validate_spec(n, NATIVE_SPECS[n])
    a = _agent(engine)
    assert capabilities().lock_key(engine.registry.spec("python"), {}, session=a.key) == ("python-kernel", a.key)


def test_an_interrupted_walter_call_is_cancelled_at_the_server(engine):
    """MCP notifications/cancelled: the server stops the call where it still can."""
    from walter_engine.tools import Exec
    sent = []
    mcp = engine.mcp

    class Proc:
        returncode = None
    mcp.proc = Proc()

    async def send(msg):
        sent.append(msg)
    mcp._send = send

    async def go():
        cancel = asyncio.Event()
        ex = Exec(engine=engine, agent=_agent(engine), call_id="c", name=W + "x", cancel=cancel)
        task = asyncio.ensure_future(mcp.call("task_update", {"task_id": "t"}, ex))
        await asyncio.sleep(0.02)
        cancel.set()
        return await task
    res = asyncio.run(go())
    assert res.is_error and res.meta == {"interrupted": True, "started": True}
    call = next(m for m in sent if m.get("method") == "tools/call")
    cancelled = next(m for m in sent if m.get("method") == "notifications/cancelled")
    assert cancelled["params"]["requestId"] == call["id"]

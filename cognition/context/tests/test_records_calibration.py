"""retrieval.records: the curated records join a plan that gets no memory but needs a lookup or is unsure (28/10)."""
import sys
import types

from walter_context import retrieval
from walter_context.plan import ContextPlan, ThreadChoice


def _plan(level="L0", caps=("tools",), conf=0.9, domains=()):
    return ContextPlan(turn_id="t", thread=ThreadChoice(id=None, new=True), act="new", level=level,
                       domains=list(domains), capabilities=list(caps), decision={"confidence": {"plan": conf}})


def _fake_memory(monkeypatch, calls):
    ctx = types.SimpleNamespace(get_context=lambda q, **kw: calls.append(kw["budget"]) or
                                {"text": "## Décisions\n- [2026-10-28] :1084", "trace": {"sections": {"records": {"refs": ["r1"]}}}})
    monkeypatch.setitem(sys.modules, "walter_memory.context", ctx)
    monkeypatch.setitem(sys.modules, "walter_memory", types.SimpleNamespace(context=ctx))


def test_records_when_lookup_needed_or_unsure(monkeypatch):
    calls = []
    _fake_memory(monkeypatch, calls)
    assert retrieval.records(_plan(caps=("tools", "memory")), "port ?").sources == ["r1"]
    assert retrieval.records(_plan(conf=0.2), "quel port ?") is not None
    assert retrieval.records(_plan(conf=0.9), "port ?") is None
    assert calls and calls[0]["records"] > 0 and calls[0]["knowledge"] == 0


def test_no_records_block_when_memory_block_runs(monkeypatch):
    monkeypatch.setattr(retrieval, "capabilities", lambda plan: None)
    monkeypatch.setattr(retrieval, "tool_cards", lambda plan: None)
    for name in ("board", "recent", "session_state", "now", "tasks", "experience"):    # no live Memory in a unit test
        monkeypatch.setattr(retrieval, name, lambda *a, **k: None)
    monkeypatch.setattr(retrieval, "subject", lambda plan: None)
    monkeypatch.setattr(retrieval, "memory", lambda plan, m: retrieval.Block("memory", 4, "m") if retrieval._gets_memory(plan) else None)
    monkeypatch.setattr(retrieval, "records", lambda plan, m: retrieval.Block("records", 4, "r"))
    ids = lambda p: [b.id for b in retrieval.gather(p, "x")[0]]          # noqa: E731
    assert ids(_plan(level="L3", caps=("tools", "memory"))) == ["memory"]
    assert ids(_plan(level="L0", caps=("tools", "memory"))) == ["records"]
    assert ids(_plan(level="L2", caps=("tools", "memory"), domains=("projects",))) == ["records"]


def test_session_state_is_layer_two_beyond_l0(monkeypatch):
    """Memory V1 P1.1 (2026-11-03): the owner's rules and the thread's working state ride in layer 2 at L1+."""
    calls = []
    ctx = types.SimpleNamespace(get_context=lambda m, **k: calls.append(k) or {"text": "État", "trace": {"sections": {}}})
    monkeypatch.setitem(sys.modules, "walter_memory.context", ctx)
    monkeypatch.setitem(sys.modules, "walter_memory", types.SimpleNamespace(context=ctx))
    b = retrieval.session_state(_plan(level="L2"), "x", "claude-code/vm/abc")
    assert b.layer == 2 and b.id == "session_state" and calls[0]["session"] == ("claude_code", "abc")
    assert calls[0]["budget"]["knowledge"] == 0 and calls[0]["budget"]["working"] > 0


def test_unsure_web_question_gets_no_memory_records(monkeypatch):
    """« Quel est le prix du Bitcoin ? » planned L0, unsure, web: the owner's records are not looked up (07/11)."""
    calls = []
    monkeypatch.setattr(retrieval, "_ctx_calls", calls, raising=False)
    import walter_memory.context as ctx
    monkeypatch.setattr(ctx, "get_context", lambda *a, **k: calls.append(k) or {"text": "x", "trace": {}})
    assert retrieval.records(_plan(caps=("tools", "web"), conf=0.2), "prix du bitcoin ?") is None
    assert retrieval.records(_plan(caps=("tools", "browser"), conf=0.2), "connecte-toi") is None
    assert retrieval.records(_plan(caps=("tools", "web", "memory"), conf=0.9), "x") is not None
    assert len(calls) == 1


def test_lone_unsure_word_gets_no_records(monkeypatch):
    import walter_memory.context as ctx
    monkeypatch.setattr(ctx, "get_context", lambda *a, **k: {"text": "x", "trace": {}})
    assert retrieval.records(_plan(conf=0.2), "test") is None
    assert retrieval.records(_plan(conf=0.2), "port du proxy mac ?") is not None

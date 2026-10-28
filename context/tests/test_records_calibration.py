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
    assert retrieval.records(_plan(caps=("tools", "search")), "port ?").sources == ["r1"]
    assert retrieval.records(_plan(conf=0.2), "port ?") is not None
    assert retrieval.records(_plan(conf=0.9), "port ?") is None
    assert calls and calls[0]["records"] > 0 and calls[0]["knowledge"] == 0


def test_no_records_block_when_memory_block_runs(monkeypatch):
    monkeypatch.setattr(retrieval, "capabilities", lambda plan: None)
    for name in ("board", "recent"):
        monkeypatch.setattr(retrieval, name, lambda *a, **k: None)
    monkeypatch.setattr(retrieval, "subject", lambda plan: None)
    monkeypatch.setattr(retrieval, "memory", lambda plan, m: retrieval.Block("memory", 4, "m") if retrieval._gets_memory(plan) else None)
    monkeypatch.setattr(retrieval, "records", lambda plan, m: retrieval.Block("records", 4, "r"))
    ids = lambda p: [b.id for b in retrieval.gather(p, "x")[0]]          # noqa: E731
    assert ids(_plan(level="L3", caps=("tools", "search"))) == ["memory"]
    assert ids(_plan(level="L0", caps=("tools", "search"))) == ["records"]
    assert ids(_plan(level="L2", caps=("tools", "search"), domains=("projects",))) == ["records"]

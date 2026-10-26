"""Step D: retrieval asks only what the plan needs, assembly orders stable → volatile and counts what is injected."""
import sys
import types

import pytest

from walter_context import retrieval
from walter_context.assembly import pack
from walter_context.plan import ContextPlan, ThreadChoice


def plan(level, thread="subject:abc", caps=("tools",), domains=()):
    return ContextPlan(turn_id="t", thread=ThreadChoice(id=thread), act="continue", level=level,
                       capabilities=list(caps), domains=list(domains))


@pytest.fixture
def sources(monkeypatch):
    calls = []
    monkeypatch.setattr(retrieval, "capabilities", lambda p: (calls.append("caps"), retrieval.Block("capabilities", 0, "M0 x10"))[1])
    monkeypatch.setattr(retrieval, "board", lambda: (calls.append("board"), retrieval.Block("subjects_board", 1, "- s1\n- s2"))[1])
    views = types.SimpleNamespace(read=lambda q: (calls.append(("view", q["depth"])),
                                                  {"depth": "overview", "content": "Titre : X", "version": 3})[1])
    context = types.SimpleNamespace(get_context=lambda m, budget, include_profile: (calls.append(("memory", budget["knowledge"])),
                                                                                    {"text": "souvenirs", "trace": {"sections": {}}})[1])
    pkg = types.ModuleType("walter_memory")
    pkg.views, pkg.context = views, context
    monkeypatch.setitem(sys.modules, "walter_memory", pkg)
    monkeypatch.setitem(sys.modules, "walter_memory.views", views)
    monkeypatch.setitem(sys.modules, "walter_memory.context", context)
    monkeypatch.setattr(retrieval, "recent", lambda key, native: retrieval.Block("recent_exchanges", 5, "Owner : oui", injected=not native))
    return calls


def test_l0_takes_capabilities_only(sources):
    blocks, notes = retrieval.gather(plan("L0"), "54 % de 89")
    assert [b.id for b in blocks] == ["capabilities"] and sources == ["caps"] and not notes


def test_depth_and_memory_follow_the_level(sources):
    blocks, _ = retrieval.gather(plan("L2"), "et la suite ?")
    assert ("view", "overview") in sources and not any(c[0] == "memory" for c in sources if isinstance(c, tuple))
    sources.clear()
    blocks, _ = retrieval.gather(plan("L4"), "tout ce qu'on a décidé")
    assert ("view", "synthesis") in sources and ("memory", 1200) in sources
    p = pack(plan("L4"), blocks)
    assert [b.layer for b in p.blocks] == sorted(b.layer for b in p.blocks)
    s = p.summary()
    assert s["tokens_session_layer"] > 0 and s["tokens_native_not_injected"] > 0       # native history: counted only
    assert "Owner : oui" not in p.text() and "souvenirs" in p.text() and "M0 x10" not in p.text()
    assert "M0 x10" in p.text(include_session_layer=True)


def test_a_failing_source_drops_only_its_block(sources, monkeypatch):
    def boom():
        raise TimeoutError("views down")
    monkeypatch.setattr(retrieval, "board", boom)
    blocks, notes = retrieval.gather(plan("L2"), "et la suite ?")
    assert "subjects_board" not in [b.id for b in blocks] and notes and notes[0].startswith("board: TimeoutError")
    assert pack(plan("L2", thread=None), [], []).text() == ""

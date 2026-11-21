"""The situation digest (19/11): the preflight's single Decision call reads Walter Memory's compact state of the
message's references when there is one (`known_state`), nothing otherwise; never for a local_only message; a late
or failed digest leaves the decision as before, said in the plan; the plan journals kinds and tokens, never lines."""
import sys
import time
import types

import pytest

from walter_context import preflight
from walter_context.preflight import Exchange, Request, run


@pytest.fixture
def wired(monkeypatch):
    calls, built = [], []

    def decide(state, questions, **kw):
        calls.append((state, kw))
        sig = {"context.act": {"choice": "new"}, "context.plan": {"choice": "thread_and_memory"},
               "context.needs": {"probabilities": {}}, "context.extensive": {"noul": 0.1},
               "context.domain": {"choice": "projects"}, "context.horizon": {"choice": "medium"},
               "router.tier": {"choice": "L2"}}
        return {"answers": {}, "signals": sig, "model": "fake", "trace": {"registry": "r", "asked": list(sig)}}

    def build(message, previous=None, previous_age_s=None, max_tokens=250, conn=None):
        built.append({"message": message, "previous": previous, "age": previous_age_s, "max": max_tokens})
        if "Sagora" in message:
            return {"lines": ["projet « Sagora » : 40 connaissances ; dernière activité 18/11"], "kinds": ["project"],
                    "tokens": 40, "cut": 0, "known": 0, "ms": 3.0}
        if "lent" in message:
            time.sleep(0.5)
        return {"lines": [], "kinds": [], "tokens": 0, "cut": 0, "known": 0, "ms": 1.0}

    llm = types.ModuleType("walter_memory.llm")
    llm.decide = decide
    dg = types.ModuleType("walter_memory.digest")
    dg.build = build
    dg.block = lambda d: {"about": "note", "lines": d["lines"]} if d.get("lines") else None
    pkg = types.ModuleType("walter_memory")
    pkg.llm, pkg.digest = llm, dg
    monkeypatch.setitem(sys.modules, "walter_memory", pkg)
    monkeypatch.setitem(sys.modules, "walter_memory.llm", llm)
    monkeypatch.setitem(sys.modules, "walter_memory.digest", dg)
    monkeypatch.setattr(preflight, "SIGNALS", "registry")
    monkeypatch.setattr(preflight, "READINGS_APART", False)
    monkeypatch.setattr(preflight, "decision_chain", lambda: ("fake",))
    monkeypatch.setattr(preflight, "owner_today", lambda: "2026-11-19")
    monkeypatch.setattr(preflight, "_anchors", lambda m: [])
    monkeypatch.setattr(preflight, "DIGEST", {"enabled": True, "max_tokens": 250, "timeout_ms": 200})
    return calls, built


def test_a_reference_adds_its_state_to_the_single_decision_call(wired):
    calls, built = wired
    p = run(Request("t", "Où en est Sagora ?", previous=Exchange("et le portail ?", "fait", 600)))
    assert len(calls) == 1                                       # one Decision call, nothing else asked
    state, _ = calls[0]
    assert state["known_state"]["lines"] == ["projet « Sagora » : 40 connaissances ; dernière activité 18/11"]
    assert built[0]["previous"] == "et le portail ?" and built[0]["age"] == 600 and built[0]["max"] == 250
    assert p.decision["digest"] == {"kinds": ["project"], "tokens": 40, "ms": 3.0}      # journaled: no line
    assert "Sagora" not in str(p.decision["digest"])


def test_nothing_is_added_when_the_digest_has_nothing(wired):
    calls, _ = wired
    p = run(Request("t", "Quelle est la capitale de l'Australie ?"))
    assert "known_state" not in calls[0][0] and p.decision["digest"]["kinds"] == []


def test_a_local_only_message_never_gets_a_digest(wired):
    calls, built = wired
    run(Request("t", "Où en est Sagora ?", privacy_class="local_only"))
    assert not built and all("known_state" not in s for s, _ in calls)


def test_a_late_digest_leaves_the_decision_as_before_and_says_so(wired):
    calls, _ = wired
    t = time.perf_counter()
    p = run(Request("t", "Un message lent"))
    assert time.perf_counter() - t < 0.45                      # bounded by timeout_ms, not by the digest
    assert "known_state" not in calls[0][0] and "late" in p.decision["digest"]


def test_switched_off_the_preflight_is_unchanged(wired, monkeypatch):
    calls, built = wired
    monkeypatch.setattr(preflight, "DIGEST", {"enabled": False, "max_tokens": 250, "timeout_ms": 200})
    p = run(Request("t", "Où en est Sagora ?"))
    assert not built and "known_state" not in calls[0][0] and "digest" not in p.decision

"""Preflight: rules without a call, the decision mapped onto a valid ContextPlan, floor, privacy, fail-open."""
import sys
import types

import pytest

from walter_context import preflight
from walter_context.preflight import Exchange, Request, fast_path, run


@pytest.fixture
def fake_llm(monkeypatch):
    calls = {"decide": [], "chat": []}
    answers = {}

    def decide(state, questions, **kw):
        calls["decide"].append((state, questions, kw))
        return {"answers": answers, "model": "fake/decider"}

    def chat(messages, **kw):
        calls["chat"].append(kw)
        return {"content": '{"level": "L3"}'}

    mod = types.ModuleType("walter_memory.llm")
    mod.decide, mod.chat = decide, chat
    pkg = types.ModuleType("walter_memory")
    pkg.llm = mod
    monkeypatch.setitem(sys.modules, "walter_memory", pkg)
    monkeypatch.setitem(sys.modules, "walter_memory.llm", mod)
    monkeypatch.setattr(preflight, "router_tasks", lambda: {"general": "Général", "coding": "Code"})
    return calls, answers


def prev(age=300):
    return Exchange(message="Je lance le lot B ?", answer="Oui", age_s=age, thread_id="th-1")


def test_rules_settle_the_obvious_without_a_call(fake_llm):
    calls, _ = fake_llm
    p = run(Request("t", "oui vas y", previous=prev()))
    assert p.fast_path == "short_reply" and p.thread.id == "th-1" and p.act == "approve" and p.level == "L1"
    assert fast_path(Request("t", "oui vas y", previous=prev(age=3 * 3600))) is None   # too old to be a reply
    # an acknowledgement followed by a real request is not a reply
    assert fast_path(Request("t", "Ok analyse complètement l'état de la VM et de walter", previous=prev())) is None
    assert fast_path(Request("t", "Oui, lance le lot 0.", previous=prev())).fast_path == "short_reply"
    for q in ("combien font 17 % de 2 340 ?", "54% de 89", "quelle heure est-il ?", "12*7"):
        assert run(Request("t", q)).fast_path == "trivial", q
    assert not calls["decide"]


def _full(answers, **over):
    answers.update({"thread": {"choice": "th-2", "confidence": 0.9, "probabilities": {"th-2": 0.7, "th-1": 0.25}},
                    "act": {"choice": "continue", "confidence": 0.9}, "level": {"choice": "L2", "confidence": 0.95},
                    "domain": {"choice": "projects", "confidence": 0.8}, "horizon": {"choice": "medium"},
                    "model_level": {"choice": "L2"}, "task": {"choice": "coding"},
                    "cap_skills": {"noul": 0.8}, "cap_search": {"noul": 0.2}, "cap_delegation": {"noul": 0.1},
                    "cap_secrets": {"noul": 0.0}})
    answers.update(over)


def test_decision_maps_onto_a_valid_plan(fake_llm):
    calls, answers = fake_llm
    _full(answers)
    p = run(Request("t", "On reprend le banc des fils sur les vrais messages", previous=prev(),
                    candidates=[{"id": "th-1", "title": "A"}, {"id": "th-2", "title": "B"}]))
    assert p.thread.id == "th-2" and p.thread.alternates == ["th-1"] and p.level == "L2" and not p.escalated
    assert p.domains == ["projects"] and p.horizons == ["medium"] and p.capabilities == ["tools", "skills"]
    assert (p.model_profile.task, p.model_profile.level) == ("coding", "L2")
    q = calls["decide"][0][1]
    assert set(q["thread"]["criteria"]) == {"th-1", "th-2", "new"} and q["cap_secrets"]["type"] == "noul"


def test_unsure_level_escalates_and_floor_keeps_the_last_exchange(fake_llm):
    calls, answers = fake_llm
    _full(answers, level={"choice": "L1", "confidence": 0.3})
    p = run(Request("t", "et pour le reste de la semaine on fait comment exactement", previous=prev()))
    assert p.escalated and p.level == "L3" and calls["chat"][0]["poste"] == "general"
    _full(answers, level={"choice": "L0", "confidence": 0.99})
    assert run(Request("t", "et pour le reste de la semaine on fait comment", previous=prev(age=600))).level == "L1"


def test_local_only_never_calls_a_cloud_model_and_failures_stay_open(fake_llm, monkeypatch):
    calls, _ = fake_llm
    p = run(Request("t", "message privé assez long pour ne pas être une réponse courte", privacy_class="local_only",
                    default_thread="session:x"))
    assert p.decision == {"skipped": "local_only"} and p.thread.id == "session:x" and not calls["decide"]

    def boom(*a, **k):
        raise TimeoutError("decisions api")
    monkeypatch.setattr(sys.modules["walter_memory.llm"], "decide", boom)
    p = run(Request("t", "une vraie question qui demande une décision du modèle"))
    assert p.level == "L1" and "TimeoutError" in p.decision["error"] and p.thread.new

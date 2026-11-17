"""Walter Decision 2.0 (17/11): the turn's questions composed from the modules' declared signals — the preflight
asks by occasion, reads the answers by signal id, keeps observations apart from the judgements; set 2 stays the
rollback (`[preflight] signals = "questions"`)."""
import sys
import types

import pytest

from walter_context import preflight
from walter_context.plan import ContextPlan
from walter_context.preflight import Exchange, Request, run


READINGS = ("context.dates", "context.people")
gate = __import__("threading").Event()


def _judged(calls):
    return next(c for c in calls if c[2].get("layers") != ["observation"])


@pytest.fixture
def registry(monkeypatch):
    calls = []
    signals = {}
    gate.set()

    def decide(state, questions, **kw):
        calls.append((state, questions, kw))
        if kw.get("layers") == ["observation"]:          # the readings, asked apart
            gate.wait(5)
            return {"answers": {}, "signals": {k: v for k, v in signals.items() if k in READINGS}, "model": "fake/reader",
                    "trace": {"asked": [k for k in signals if k in READINGS], "unavailable": {}}}
        return {"answers": {}, "signals": dict(signals), "model": "fake/decider",
                "parts": [{"model": "fake/decider"}, {"model": "fake/reader"}],
                "trace": {"registry": "r1", "asked": list(signals), "skipped": {"context.thread": "when: threads"},
                          "unavailable": {}}}

    mod = types.ModuleType("walter_memory.llm")
    mod.decide = decide
    pkg = types.ModuleType("walter_memory")
    pkg.llm = mod
    monkeypatch.setitem(sys.modules, "walter_memory", pkg)
    monkeypatch.setitem(sys.modules, "walter_memory.llm", mod)
    monkeypatch.setattr(preflight, "SIGNALS", "registry")
    monkeypatch.setattr(preflight, "decision_chain", lambda: ("fake/decider",))
    monkeypatch.setattr(preflight, "owner_today", lambda: "2026-11-17")
    return calls, signals


MSG = "Rappelle-moi jeudi d'appeler Sophie pour le devis"


def _answers(signals, **over):
    signals.update({
        "context.act": {"choice": "new", "confidence": 0.9}, "context.plan": {"choice": "thread_and_memory"},
        "context.extensive": {"noul": 0.1}, "context.domain": {"choice": "agenda"}, "context.horizon": {"choice": "day"},
        "context.needs": {"choices": ["memory"], "probabilities": {"memory": 0.8, "web": 0.1, "secrets": 0.6}},
        "router.tier": {"choice": "L2"}, "memory.work": {"noul": 0.7},
        "context.dates": {"spans": [{"text": "jeudi", "found": 0.97, "date": "2026-11-19", "past": "2026-11-12",
                                     "ambiguous": True, "read_by": "walter"},
                                    {"text": "lundi", "found": 0.9, "date": "2026-11-23"},     # not in the message
                                    {"text": "Rappelle", "found": 0.2},                         # too unsure
                                    {"text": "appeler", "found": 0.6}]},                        # names no day
        "context.people": {"spans": [{"text": "Sophie", "found": 0.95}, {"text": "sophie", "found": 0.9}]},
        "context.thread": None, **over})


def test_the_turn_is_asked_by_occasion_with_the_callers_facts_and_options(registry):
    calls, signals = registry
    _answers(signals)
    cands = [{"id": "th-1", "title": "Devis cuisine", "task": "relancer"}, {"id": "th-2", "title": "Router"}]
    run(Request("t", MSG, candidates=cands, previous=Exchange("et le devis ?", "en attente", 600, "th-1")))
    state, questions, kw = _judged(calls)
    assert questions is None and kw["occasion"] == "turn" and kw["focus"] == "new_message" and kw["now"] == "2026-11-17"
    assert kw["facts"] == ["threads", "open_task"] and kw["layers"] == ["inference"]
    rs, _, rkw = next(c for c in calls if c[2].get("layers") == ["observation"])
    assert rs == {"new_message": MSG} and rkw["samples"] == preflight.READINGS_SAMPLES and "options" not in rkw
    assert rkw.get("sampling") == ("first" if preflight.READINGS_SAMPLES > 1 else None)   # the message alone, hedged
    assert kw["options"]["threads"] == {"th-1": "continues: Devis cuisine — the thread of the previous exchange",
                                        "th-2": "continues: Router"}
    assert state["new_message"] == MSG


def test_answers_by_signal_make_the_same_plan_and_observations_stay_apart(registry):
    _, signals = registry
    _answers(signals)
    p = run(Request("t", MSG))
    assert p.act == "new" and p.level == "L3" and p.model_profile.level == "L2"
    assert p.capabilities == ["tools", "memory", "secrets"]           # one several-options question, ≥ 0.5 each
    assert p.observations == {"dates": [{"text": "jeudi", "date": "2026-11-19", "past": "2026-11-12",
                                         "ambiguous": True, "found": 0.97}],
                              "people": [{"text": "Sophie", "found": 0.95}]}
    rd = p.decision["signals"].pop("readings")
    assert p.decision["signals"] == {"registry": "r1", "asked": 11, "skipped": ["context.thread"]}
    assert rd["asked"] == 2 and rd["model"] == "fake/reader" and rd["ms"] >= 0
    assert p.decision["parts"] == ["fake/decider", "fake/reader"] and p.decision["work"] == 0.7
    assert ContextPlan.from_dict(p.to_dict() if hasattr(p, "to_dict") else __import__("dataclasses").asdict(p))


def test_a_reading_said_unavailable_leaves_no_observation_and_the_plan_stands(registry):
    _, signals = registry
    _answers(signals, **{"context.dates": None, "context.people": None})
    p = run(Request("t", MSG))
    assert p.observations == {} and p.act == "new" and not p.decision.get("degraded")


def test_no_judgement_at_all_is_the_degraded_plan_said(registry):
    _, signals = registry
    p = run(Request("t", MSG))
    assert p.decision.get("degraded") is True


def test_set_2_stays_the_rollback(registry, monkeypatch):
    calls, _ = registry
    monkeypatch.setattr(preflight, "SIGNALS", "questions")
    monkeypatch.setattr(preflight, "router_tasks", lambda: {})
    run(Request("t", MSG))
    _, questions, kw = calls[0]
    assert len(calls) == 1 and "act" in questions and "occasion" not in kw


def test_the_plan_does_not_wait_for_the_readings_the_pack_does(registry):
    from walter_context import retrieval
    _, signals = registry
    _answers(signals)
    gate.clear()                                        # the readings are slow
    p = run(Request("t", MSG), readings="apart")
    assert p.act == "new" and p.observations == {} and p._readings is not None
    gate.set()
    assert p._readings.settle(p, 2) and p.observations["dates"][0]["date"] == "2026-11-19"
    assert "19 novembre 2026" in retrieval.now(plan=p).text


def test_readings_still_running_when_the_answer_leaves_are_said_late(registry):
    _, signals = registry
    _answers(signals)
    gate.clear()
    p = run(Request("t", MSG), readings="apart")
    p._readings.late(p)
    gate.set()
    assert p.observations == {} and p.decision["signals"]["readings"] == {"late": True}
    assert not p._readings.settle(p, 0) or p.observations == {}       # a late result is dropped, never half-applied


def test_one_call_carries_both_when_readings_are_not_apart(registry, monkeypatch):
    calls, signals = registry
    _answers(signals)
    monkeypatch.setattr(preflight, "READINGS_APART", False)
    p = run(Request("t", MSG))
    assert len(calls) == 1 and "layers" not in calls[0][2] and p.observations["people"][0]["text"] == "Sophie"



def test_the_pack_waits_for_the_readings_from_the_message_not_from_its_own_step(registry, monkeypatch):
    # 17/11 bench: a 2 s wait counted from the pack's step put two slow readings (1.8–3.6 s) on the answer's total
    import time
    from walter_context import retrieval
    _, signals = registry
    _answers(signals)
    gate.clear()
    p = run(Request("t", MSG), readings="apart")
    seen = []
    real = p._readings.settle
    monkeypatch.setattr(p._readings, "settle", lambda plan, timeout=0.0: seen.append(timeout) or real(plan, 0))
    for name in ("capabilities", "tool_cards", "people", "tasks", "experience", "records", "board", "session_state",
                 "subject", "memory", "recent"):
        monkeypatch.setattr(retrieval, name, lambda *a, **k: None)
    monkeypatch.setitem(retrieval.PACK, "readings_wait_s", 1.0)
    p._readings.t0 = time.perf_counter() - 0.9               # the message came 0.9 s ago
    retrieval.gather(p, MSG)
    assert seen and all(t <= 0.11 for t in seen)              # what is left of the 1 s, not 1 s more
    p._readings.t0 = time.perf_counter() - 5
    t = time.perf_counter()
    retrieval.gather(p, MSG)
    assert time.perf_counter() - t < 0.5 and p.observations == {}    # long past: no wait, the readings stay out
    gate.set()


def test_readings_can_be_hedged(registry, monkeypatch):
    calls, signals = registry
    _answers(signals)
    monkeypatch.setattr(preflight, "READINGS_SAMPLES", 2)
    p = run(Request("t", MSG), readings="apart")
    p._readings.settle(p, 2)
    read = next(c for c in calls if c[2].get("layers") == ["observation"])
    assert read[2]["samples"] == 2 and read[2]["sampling"] == "first"


def test_the_plan_follows_the_decision_resolver_and_carries_its_trace(registry, monkeypatch):
    """§6 (17/11): the gateway resolves the answers against the declared relations; the plan reads the resolved
    answers (not the raw ones) and journals which relation changed what — names only."""
    calls, signals = registry
    _answers(signals, **{"context.plan": {"choice": "none"}, "context.extensive": {"noul": 0.9}})
    resolved = {**signals, "context.plan": {"choice": "thread_and_memory", "resolved_by": "context.needs_memory_plan"},
                "context.extensive": None}
    base = sys.modules["walter_memory.llm"].decide

    def decide(state, questions, **kw):
        res = base(state, questions, **kw)
        if kw.get("layers") != ["observation"]:
            res["resolution"] = {"signals": resolved, "changed": {
                "context.plan": {"by": ["context.needs_memory_plan"]}, "context.extensive": {"by": ["context.extensive_needs_thread"]}},
                "conflicts": [{"relation": "context.needs_memory_plan"}], "uncertain_relations": [], "uncertain": [],
                "missing": [], "set_aside": [{"signal": "context.extensive"}]}
        return res
    monkeypatch.setattr(sys.modules["walter_memory.llm"], "decide", decide)
    monkeypatch.setattr(preflight, "_anchors", lambda m: ["Orme"])
    p = run(Request("t", MSG))
    assert p.level == "L3"                                   # resolved plan; the set-aside « extensive » makes no L4
    assert p.decision["resolution"] == {"changed": {"context.plan": ["context.needs_memory_plan"],
                                                    "context.extensive": ["context.extensive_needs_thread"]},
                                        "conflicts": ["context.needs_memory_plan"], "set_aside": ["context.extensive"]}
    assert "anchor.memory" in _judged(calls)[2]["facts"]     # the deterministic fact the relation reads
    assert p.decision["anchors"] == ["Orme"]


def test_an_unsettled_conflict_is_said_to_the_model_in_the_modules_own_words():
    from walter_context.assembly import Pack
    from walter_context.preflight import resolution_brief
    rb = resolution_brief({"resolution": {"signals": {}, "changed": {}, "conflicts": [
        {"relation": "context.new_subject_new_thread", "settled": None, "use": "un sujet neuf et un fil existant"}],
        "uncertain_relations": [], "uncertain": [], "missing": [], "set_aside": []}})
    assert rb["unsettled"] == ["un sujet neuf et un fil existant"]
    p = run(Request("t", "bonjour"))
    p.decision["resolution"] = rb
    assert "un sujet neuf et un fil existant" in Pack(plan=p).lead

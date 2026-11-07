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
    monkeypatch.setattr(preflight, "decision_chain", lambda: ("fake/decider",))
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
                    "act": {"choice": "continue", "confidence": 0.9}, "plan": {"choice": "thread", "confidence": 0.95},
                    "extensive": {"noul": 0.1},
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


def test_unsure_plan_stays_one_decision_call_and_floor_keeps_the_last_exchange(fake_llm):
    calls, answers = fake_llm
    _full(answers, plan={"choice": "last_exchange", "confidence": 0.3})
    p = run(Request("t", "et pour le reste de la semaine on fait comment exactement", previous=prev()))
    assert not p.escalated and p.level == "L1" and not calls["chat"] and len(calls["decide"]) == 1
    assert calls["decide"][0][2]["models"] == ("fake/decider",)
    _full(answers, plan={"choice": "none", "confidence": 0.99})
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


def test_extensive_search_lifts_a_thread_plan_to_l4(fake_llm):
    calls, answers = fake_llm
    _full(answers, extensive={"noul": 0.8})
    assert run(Request("t", "retrouve tout ce qu'on a décidé sur la mémoire depuis septembre", previous=prev())).level == "L4"


def test_router_answers_are_cached_and_refreshed_off_the_message_path(tmp_path, monkeypatch):
    import json
    import time
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(preflight, "_ROUTER", None)
    monkeypatch.setattr(preflight, "_ROUTER_SEEN", [0.0, 0.0])
    spawned = []

    class Proc:
        def __init__(self, args, **kw):
            spawned.append(args)
            self.out = json.dumps([{"task": "general", "label": "Général", "interface": "chat"}]
                                  if args[1:] == ["tasks"] else {"chain": ["a/decider", "b/decider"]})

        def communicate(self, timeout=None):
            return self.out, ""

    monkeypatch.setattr(preflight.subprocess, "Popen", Proc)
    assert preflight.router_tasks() == {"general": "Général"} and preflight.decision_chain() == ("a/decider", "b/decider")
    assert len(spawned) == 2 and (tmp_path / "walter-context" / "router.json").exists()
    monkeypatch.setattr(preflight, "_ROUTER", None)
    spawned.clear()
    assert preflight.decision_chain() == ("a/decider", "b/decider") and not spawned        # fresh: disk only
    cache = tmp_path / "walter-context" / "router.json"
    cache.write_text(json.dumps({**json.loads(cache.read_text()), "at": time.time() - 3600}))
    monkeypatch.setattr(preflight, "_ROUTER_SEEN", [0.0, 0.0])
    assert preflight.decision_chain() == ("a/decider", "b/decider")                       # stale copy used now
    assert len(spawned) == 1 and "--refresh-router" in spawned[0]                           # refreshed detached
    preflight.decision_chain()
    assert len(spawned) == 1                                   # a long-lived process refreshes once per period
    cache.write_text(json.dumps({"at": time.time(), "tasks": {}, "chain": ["c/decider"]}))
    assert preflight.decision_chain() == ("c/decider",)                                    # new file read back


def test_service_answers_like_the_cli_and_records_shadow_plans(fake_llm, monkeypatch, tmp_path):
    import json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from walter_context.preflight import __main__ as cli
    from walter_context.preflight import service
    calls, answers = fake_llm
    _full(answers)
    monkeypatch.setattr(service, "_router", lambda: {"chain": ["fake/decider"]})
    monkeypatch.setattr(cli, "_STATE", [tmp_path])
    srv = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(path, body):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    try:
        status, body = post("/preflight", {"message": "On reprend le banc des fils sur les vrais messages"})
        assert status == 200 and json.loads(body)["level"] == "L2"
        status, body = post("/preflight?shadow=1", {"message": "oui vas y", "runtime": "claude_code"})
        assert status == 204 and not body
        rows = [json.loads(x) for f in tmp_path.glob("preflight-*.jsonl") for x in f.read_text().splitlines()]
        assert len(rows) == 1 and rows[0]["runtime"] == "claude_code" and "plan" in rows[0]
        with urllib.request.urlopen(base + "/health", timeout=5) as r:
            assert json.loads(r.read()) == {"ok": True, "router_cached": True}
    finally:
        srv.shutdown()


def test_named_project_forces_memory(monkeypatch):
    """A decision model that reads « Le site EDGEWISE, c'est où ? » as a web question still gets the owner's memory."""
    from walter_context import preflight as pf
    monkeypatch.setattr(pf, "_anchors", lambda m: ["edgewise"] if "edgewise" in m.lower() else [])
    monkeypatch.setattr(pf, "router_tasks", lambda: {})
    monkeypatch.setattr(pf, "decision_chain", lambda: None)
    import walter_memory.llm as llm
    answers = {"act": {"choice": "new"}, "plan": {"choice": "none", "confidence": 0.8}, "cap_web": {"noul": 0.9}}
    monkeypatch.setattr(llm, "decide", lambda *a, **k: {"answers": answers, "model": "fake"})
    p = pf.run(pf.Request(turn_id="t", message="Le site EDGEWISE, c'est quoi et il est où ?"))
    assert p.capabilities[:2] == ["tools", "memory"] and "web" in p.capabilities
    assert p.decision["anchors"] == ["edgewise"]
    q = pf.run(pf.Request(turn_id="t2", message="Quel est le prix du Bitcoin ?"))
    assert "memory" not in q.capabilities and "anchors" not in q.decision

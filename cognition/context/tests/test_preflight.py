"""Preflight: rules without a call, the decision mapped onto a valid ContextPlan, floor, privacy, fail-open."""
import json
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



def _boom(*a, **k):
    raise TimeoutError("decisions api https://openrouter.ai/x failed, see /walter/cognition/memory/.env sk-abcdefghijklmnop")


def test_a_failed_decision_gives_an_explicit_prudent_plan(fake_llm, monkeypatch):
    """SOCLE A2 (11/11: 9 owner turns silently served as L1 / general L1): the plan says it is degraded, is L3 with
    tools + memory, keeps a close subject found locally, and asks general/L2 when no recent profile is known."""
    monkeypatch.setattr(sys.modules["walter_memory.llm"], "decide", _boom)
    cands = [{"id": "subject:a", "similarity": 0.81}, {"id": "subject:b", "similarity": 0.4}]
    p = run(Request("t", "une vraie question qui demande une décision du modèle", candidates=cands))
    d = p.decision
    assert d["degraded"] is True and d["error"].startswith("TimeoutError: ")
    assert "openrouter" not in d["error"] and "/walter" not in d["error"] and "sk-abc" not in d["error"]
    assert len(d["error"]) <= 120
    assert p.level == "L3" and p.capabilities == ["tools", "memory"] and not p.escalated and p.fast_path is None
    assert (p.model_profile.task, p.model_profile.level) == ("general", "L2") and d["profile_from"] == "default"
    assert p.thread.id == "subject:a" and d["thread_by"] == "similarity"
    # no candidate close enough: no thread claim (a new one), the session's recent profile is reused
    p = run(Request("t", "une autre question", candidates=[{"id": "subject:b", "similarity": 0.3}],
                    previous_profile={"task": "coding", "level": "L3"}))
    assert p.thread.new and p.decision["thread_by"] == "none"
    assert (p.model_profile.task, p.model_profile.level) == ("coding", "L3") and p.decision["profile_from"] == "previous_run"
    # an empty or malformed decision is a failure too, never a KeyError out of the preflight
    monkeypatch.setattr(sys.modules["walter_memory.llm"], "decide", lambda *a, **k: {"model": "x"})
    assert run(Request("t", "encore une question longue")).decision["degraded"] is True


def test_degraded_plan_is_recorded_signalled_and_announced_in_the_pack(fake_llm, monkeypatch, tmp_path):
    from walter_context.preflight import __main__ as cli
    from walter_context import retrieval
    monkeypatch.setattr(sys.modules["walter_memory.llm"], "decide", _boom)
    monkeypatch.setattr(cli, "_STATE", [tmp_path])
    monkeypatch.setattr(cli, "subjects", lambda d: ([], None, None))
    monkeypatch.setattr(cli, "last_exchange", lambda key, message: None)
    emitted, updates = [], []
    bus = types.ModuleType("walter_memory.bus")
    bus.emit = lambda *a, **k: emitted.append((a, k))
    sys.modules["walter_memory"].bus = bus
    monkeypatch.setitem(sys.modules, "walter_memory.bus", bus)
    monkeypatch.setattr(cli.subprocess, "run", lambda args, **kw: updates.append(json.loads(kw["input"])))
    monkeypatch.setattr(retrieval, "gather", lambda plan, msg, **kw: (
        [retrieval.Block("memory", 4, "souvenirs"), retrieval.Block("now", 5, "Maintenant : x")], []))
    d = {"message": "une vraie question qui demande une décision", "runtime": "dsh", "session_id": "dsh/vm/s1",
         "run_id": "r1", "turn_id": "dsh/vm/s1:1"}
    plan, row = cli.handle(d, shadow=False, want_pack=True)
    assert plan["decision"]["degraded"] and row["degraded"] and plan["level"] == "L3"
    assert row["pack_text"].startswith("Attention : l'intention de ce message n'a pas pu être évaluée")
    assert row["pack"]["degraded"] is True
    assert updates[0]["requested"]["degraded"] is True and updates[0]["level"] == "L3"
    (typ, source, subject, payload), kw = emitted[0]
    assert typ == "context.degraded" and source == "walter-context" and subject == "dsh/vm/s1"
    assert payload["run_id"] == "r1" and "message" not in payload and kw["dedupe_key"] == "context.degraded:dsh/vm/s1:1"
    rows = [json.loads(x) for f in tmp_path.glob("preflight-*.jsonl") for x in f.read_text().splitlines()]
    assert rows[-1]["plan"]["decision"]["degraded"] is True
    # a second consecutive failure, with the bus down too, neither raises nor blocks the turn
    bus.emit = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("bus down"))
    plan, row = cli.handle({**d, "turn_id": "dsh/vm/s1:2"}, shadow=False, want_pack=True)
    assert plan["decision"]["degraded"] and row["pack_text"]
    from walter_context.shadow import report
    r = report(tmp_path)
    assert r["degraded"] == 2 and r["fast_paths"] == {"degraded": 2} and r["degraded_errors"] == {"TimeoutError": 2}


def test_degraded_profile_is_the_sessions_previous_one_when_recent(monkeypatch, tmp_path):
    import time as _t
    from walter_context.preflight import __main__ as cli
    monkeypatch.setattr(cli, "_STATE", [tmp_path])
    monkeypatch.setattr(cli, "_PROFILES", {"dsh/vm/s1": (_t.time() - 60, {"task": "coding", "level": "L3"})})
    assert cli.previous_profile("dsh/vm/s1") == {"task": "coding", "level": "L3"}
    monkeypatch.setattr(cli, "_PROFILES", {"dsh/vm/s1": (_t.time() - 7200, {"task": "coding", "level": "L3"})})
    assert cli.previous_profile("dsh/vm/s1") is None
    # a restarted service reads its own journal
    from datetime import datetime, timezone
    monkeypatch.setattr(cli, "_PROFILES", {})
    (tmp_path / f"preflight-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl").write_text(json.dumps(
        {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "runtime": "dsh", "session_id": "dsh/vm/s2",
         "plan": {"model_profile": {"task": "general", "level": "L1"}, "decision": {"model": "m"}}}) + "\n")
    assert cli.previous_profile("dsh/vm/s2") == {"task": "general", "level": "L1"}
    assert cli.previous_profile("dsh/vm/other") is None


def test_previous_exchange_is_read_from_the_session_when_the_caller_sends_none(fake_llm, monkeypatch, tmp_path):
    """The engine sends previous: null; the preflight reads the last exchange itself so short replies and the plan
    floor work on the production path. The new message, if already journaled, is not its own previous exchange."""
    from datetime import datetime, timedelta, timezone
    from walter_context.preflight import __main__ as cli
    now = datetime.now(timezone.utc)
    evs = {"events": [{"type": "user/message", "text": "Je lance le lot B ?", "occurred_at": now - timedelta(minutes=6)},
                      {"type": "assistant/message", "text": "Oui, prêt." + "x" * 3000, "occurred_at": now - timedelta(minutes=5)},
                      {"type": "user/message", "text": "oui vas y", "occurred_at": now}]}
    ex = cli.last_exchange("dsh/vm/s1", "oui vas y", reader=lambda: evs)
    assert ex["message"] == "Je lance le lot B ?" and len(ex["answer"]) == 1200 and 250 < ex["age_s"] < 350
    assert cli.last_exchange("k", "x", reader=lambda: {"events": []}) is None
    calls, _ = fake_llm
    monkeypatch.setattr(cli, "_STATE", [tmp_path])
    monkeypatch.setattr(cli, "subjects", lambda d: ([], "subject:a", 300.0))
    monkeypatch.setattr(cli, "last_exchange", lambda key, message: {"message": "Je lance le lot B ?", "answer": "Oui",
                                                                     "age_s": 300.0})
    plan, row = cli.handle({"message": "oui vas y", "runtime": "dsh", "session_id": "dsh/vm/s1", "previous": None},
                           shadow=True)
    assert plan["fast_path"] == "short_reply" and plan["thread"]["id"] == "subject:a" and row["previous"] == "fetched"
    assert not calls["decide"]

    def slow(key, message):
        import time as _t
        _t.sleep(0.5)
    monkeypatch.setattr(cli, "last_exchange", slow)
    monkeypatch.setitem(cli.SETTINGS, "previous_timeout_s", 0.05)
    plan, row = cli.handle({"message": "oui vas y", "runtime": "dsh", "session_id": "dsh/vm/s1"}, shadow=True)
    assert row["previous"] == "failed: TimeoutError" and plan is not None


def test_an_approval_or_a_correction_stays_in_the_thread_of_the_exchange_it_answers(fake_llm):
    """12/11: « ok vas-y pour la première seulement » was sent to another subject by an unsure thread pick."""
    calls, answers = fake_llm
    cands = [{"id": "th-1", "title": "Lot B"}, {"id": "th-9", "title": "Autre sujet"}]
    _full(answers, act={"choice": "approve"}, thread={"choice": "th-9", "confidence": 0.29})
    p = run(Request("t", "ok vas-y pour la première seulement, décris-la en une phrase", previous=prev(), candidates=cands))
    assert p.thread.id == "th-1" and p.thread.alternates == ["th-9"] and p.decision["thread_by"] == "previous_exchange"
    _full(answers, act={"choice": "continue"}, thread={"choice": "th-9", "confidence": 0.9})
    p = run(Request("t", "et pour l'autre sujet, où en est-on exactement ce matin ?", previous=prev(), candidates=cands))
    assert p.thread.id == "th-9" and "thread_by" not in p.decision          # a continuation may change subject
    _full(answers, act={"choice": "approve"}, thread={"choice": "th-9", "confidence": 0.9})
    p = run(Request("t", "ok vas-y pour la première seulement, décris-la en une phrase", previous=prev(age=86400), candidates=cands))
    assert p.thread.id == "th-9"                                            # an old exchange is not « the previous »
    # the previous exchange's thread is named to the decision model on its own line
    assert "the thread of the previous exchange" in calls["decide"][-2][1]["thread"]["criteria"]["th-1"]
    assert "previous exchange" not in calls["decide"][-2][1]["thread"]["criteria"]["th-9"]
    # a continuation the model hesitates on (no majority) stays where the conversation is; a clear switch is honoured
    _full(answers, act={"choice": "continue"},
          thread={"choice": "th-9", "confidence": 0.45, "probabilities": {"th-9": 0.45, "th-1": 0.35, "new": 0.2}})
    p = run(Request("t", "décris la première étape en une phrase, sans outil", previous=prev(), candidates=cands))
    assert p.thread.id == "th-1" and p.thread.alternates == ["th-9"] and p.decision["thread_by"] == "previous_exchange_alternate"
    _full(answers, act={"choice": "continue"},
          thread={"choice": "th-9", "confidence": 0.7, "probabilities": {"th-9": 0.7, "th-1": 0.25}})
    p = run(Request("t", "décris la première étape en une phrase, sans outil", previous=prev(), candidates=cands))
    assert p.thread.id == "th-9" and "thread_by" not in p.decision


def test_the_decision_says_whether_the_message_is_work_to_keep_as_a_task(fake_llm):
    """SOCLE A3: the Run Plane opens a durable task on the preflight's own judgement, not on the Router tier."""
    from walter_context.preflight.__main__ import requested
    calls, answers = fake_llm
    _full(answers, work={"noul": 0.9}, task={"choice": "general"}, model_level={"choice": "L1"})
    p = run(Request("t", "Range mes notes en trois étapes et écris le résultat dans un fichier", previous=prev()))
    assert "work" in calls["decide"][-1][1] and p.decision["work"] == 0.9
    assert requested(p.to_dict(), "x")["work"] is True            # a general / L1 request can still be a task
    _full(answers, work={"noul": 0.1}, task={"choice": "coding"})
    assert requested(run(Request("t", "Tu en penses quoi de ce code, en deux mots ?", previous=prev())).to_dict(), "x")["work"] is False
    answers.pop("work")
    assert "work" not in requested(run(Request("t", "Une question sans jugement de travail ici", previous=prev())).to_dict(), "x")


def test_the_effort_of_a_turn_is_not_its_context_level(fake_llm):
    """SOCLE A7 (2026-11-12): a request that needs nothing beyond its own message can still be long work — the
    ceilings follow what must be DONE (`decision.effort`), the level what must be SEEN."""
    calls, answers = fake_llm
    _full(answers, plan={"choice": "none"}, work={"noul": 0.9}, model_level={"choice": "L2"})
    p = run(Request("t", "Recherche trois options, compare-les, choisis la meilleure et écris le résultat dans un fichier"))
    assert p.level == "L0" and p.decision["effort"] == "L4"            # work to carry out: the general ceilings
    _full(answers, plan={"choice": "none"}, work={"noul": 0.1}, model_level={"choice": "L2"})
    assert run(Request("t", "Compare ces deux formulations et dis laquelle est la plus claire")).decision["effort"] == "L2"
    _full(answers, plan={"choice": "none"}, work={"noul": 0.1}, model_level={"choice": "L1"})
    p = run(Request("t", "Quelle est la capitale de l'Australie, en un mot ?"))
    assert p.level == "L0" and p.decision["effort"] == "L0"            # a light question keeps the light ceilings
    _full(answers, plan={"choice": "thread_and_memory"}, work={"noul": 0.1}, model_level={"choice": "L1"})
    assert run(Request("t", "Rappelle-moi ce qu'on avait dit sur le budget", previous=prev())).decision["effort"] == "L3"


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
                                  if args[1:] == ["tasks"] else {"chain": ["a/decider", "b/decider"]}
                                  if args[1:] == ["decision-chain"] else
                                  {"notes": [{"module": "memory", "level": "M0", "content": "- **Memory** — x"}]})

        def communicate(self, timeout=None):
            return self.out, ""

    monkeypatch.setattr(preflight.subprocess, "Popen", Proc)
    assert preflight.router_tasks() == {"general": "Général"} and preflight.decision_chain() == ("a/decider", "b/decider")
    assert len(spawned) == 3 and (tmp_path / "walter-context" / "router.json").exists()
    assert preflight.module_lines() == [{"module": "memory", "line": "- **Memory** — x"}]
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


def test_memory_needed_lifts_the_plan_to_the_level_that_carries_memory(fake_llm):
    """2026-11-09: the decision model answered « memory needed » with « nothing beyond the message » in the same call
    on 13 of the 29 bench messages; the plan follows the specific question. Without memory the level is untouched."""
    calls, answers = fake_llm
    answers.update({"act": {"choice": "new"}, "plan": {"choice": "none", "confidence": 0.6},
                    "cap_memory": {"noul": 0.8}})
    p = run(Request(turn_id="t", message="Qui décide si un message que je reçois mérite une notification ?"))
    assert p.level == "L3" and "memory" in p.capabilities
    assert calls["decide"][0][2]["samples"] == preflight.DECISION_SAMPLES >= 3
    answers["cap_memory"] = {"noul": 0.2}
    assert run(Request(turn_id="t2", message="Traduis « bonjour » en espagnol")).level == "L0"
    answers.update({"plan": {"choice": "thread_and_memory"}, "extensive": {"noul": 0.9}, "cap_memory": {"noul": 0.9}})
    assert run(Request(turn_id="t3", message="Fais le point complet sur mes projets")).level == "L4"


def test_the_answer_comes_within_the_time_the_caller_waits(fake_llm, monkeypatch, tmp_path):
    """13/11: the engine waits 7 s; the run was attached then the pack read, in line, after the decision — the answer
    came 1.5 s too late and the turn went on without its plan. The caller's wait bounds the whole answer: a decision
    that is not there in time gives the degraded plan (said), a slow run attachment is not waited for."""
    import time
    from walter_context.preflight import __main__ as cli
    from walter_context import retrieval
    assert cli.answer_within(None) == cli.SETTINGS["answer_within_s"]
    assert cli.answer_within(7000) == min(cli.SETTINGS["answer_within_s"], 7 - cli.SETTINGS["answer_margin_s"])
    assert cli.answer_within(3000) == 3 - cli.SETTINGS["answer_margin_s"] and cli.answer_within(200) == 1.0
    assert cli.answer_within(True) == cli.SETTINGS["answer_within_s"]
    monkeypatch.setattr(cli, "_STATE", [tmp_path])
    monkeypatch.setattr(cli, "subjects", lambda d: ([], None, None))
    monkeypatch.setattr(cli, "last_exchange", lambda key, message: None)
    monkeypatch.setattr(cli, "_signal_degraded", lambda d, plan: None)
    seen = {}
    monkeypatch.setattr(cli, "_attach_run", lambda *a: (time.sleep(4), seen.setdefault("attached", True)))
    monkeypatch.setattr(retrieval, "gather", lambda plan, msg, **kw: (
        seen.setdefault("deadline", kw.get("deadline")), ([retrieval.Block("now", 5, "Maintenant : x")], []))[1])
    real = sys.modules["walter_memory.llm"].decide
    monkeypatch.setattr(sys.modules["walter_memory.llm"], "decide", lambda *a, **k: (time.sleep(5), real(*a, **k))[1])
    d = {"message": "une vraie question qui demande une décision", "runtime": "dsh", "session_id": "dsh/vm/s9",
         "run_id": "r9", "turn_id": "dsh/vm/s9:1", "answer_within_ms": 2500}
    t0 = time.monotonic()
    plan, row = cli.handle(d, shadow=False, want_pack=True)
    took = time.monotonic() - t0
    assert took < 2.5, took
    assert plan["decision"]["degraded"] and "no decision within" in plan["decision"]["error"]
    assert row["pack_text"].startswith("Attention : l'intention de ce message")
    assert row["run_attach"] == "late" and "attached" not in seen and row["total_ms"] < 2500
    assert seen["deadline"] is not None


def test_a_resumption_is_judged_when_a_thread_shows_a_task_and_travels_to_the_run_plane(fake_llm):
    """13/11 (live engine): « reprends la tâche … » through another interface has no previous exchange there; its act
    came back « new » and a second objective was opened. The preflight judges the resumption itself, only when a
    thread shows an open or suspended task, and says it to the Run Plane (`requested.resume`)."""
    from walter_context.preflight import __main__ as cli
    calls, answers = fake_llm
    plain = [{"id": "th-1", "title": "Lot B"}, {"id": "th-9", "title": "Autre sujet"}]
    _full(answers, act={"choice": "new"}, thread={"choice": "th-1", "confidence": 0.64})
    p = run(Request("t", "reprends la tâche du lot B là où elle s'est arrêtée et termine-la", candidates=plain))
    assert "resume" not in calls["decide"][-1][1] and "resume" not in p.decision      # no task shown: not asked
    carrying = [{"id": "th-1", "title": "Lot B", "task": "tâche suspendue (interrompue) — déploie le lot B"}, plain[1]]
    _full(answers, act={"choice": "new"}, thread={"choice": "th-1", "confidence": 0.64}, resume={"noul": 0.91},
          work={"noul": 0.97})
    p = run(Request("t", "reprends la tâche du lot B là où elle s'est arrêtée et termine-la", candidates=carrying))
    state, q, _ = calls["decide"][-1]
    assert "resume" in q and state["threads"]["th-1"]["task"].startswith("tâche suspendue")
    assert p.decision["resume"] == 0.91 and p.thread.id == "th-1"
    assert cli.requested(p.to_dict(), "m")["resume"] is True and cli.requested(p.to_dict(), "m")["work"] is True
    _full(answers, act={"choice": "new"}, thread={"choice": "th-1", "confidence": 0.64}, resume={"noul": 0.1})
    p = run(Request("t", "dans le lot B, ajoute aussi une page d'aide", candidates=carrying))
    assert "resume" not in cli.requested(p.to_dict(), "m")                            # another piece of work
    # a task that is its own thread (no subject yet) asks the question too
    own = [{"id": "task:42", "kind": "task", "title": "déploie le lot B", "state": "tâche suspendue"}]
    run(Request("t", "reprends la tâche du lot B là où elle s'est arrêtée et termine-la", candidates=own))
    assert "resume" in calls["decide"][-1][1]


def test_a_degraded_plan_stays_in_the_thread_of_a_recent_exchange(fake_llm, monkeypatch):
    """13/11: the decision did not come in time 3 s after an exchange; the closest subject in words was another one
    and the task of the exchange lost its follow-up. Nobody judged: the conversation stays where it is."""
    monkeypatch.setattr(sys.modules["walter_memory.llm"], "decide", _boom)
    cands = [{"id": "subject:a", "similarity": 0.81}, {"id": "subject:b", "similarity": 0.6}]
    p = run(Request("t", "continue la tâche : fais maintenant la deuxième étape", candidates=cands,
                    default_thread="subject:b", waiting_age_s=3.5))
    assert p.thread.id == "subject:b" and p.thread.alternates == ["subject:a"]
    assert p.decision["degraded"] and p.decision["thread_by"] == "previous_exchange"
    p = run(Request("t", "continue la tâche : fais maintenant la deuxième étape", candidates=cands,
                    default_thread="subject:b", waiting_age_s=7200))
    assert p.thread.id == "subject:a" and p.decision["thread_by"] == "similarity"      # an old exchange: the words


def test_the_decision_is_given_the_time_the_caller_has(fake_llm):
    calls, answers = fake_llm
    _full(answers)
    run(Request("t", "une vraie question qui demande une décision du modèle"), within=3.2)
    assert calls["decide"][-1][2]["timeout"] == 3.2
    run(Request("t", "une vraie question qui demande une décision du modèle"))
    assert calls["decide"][-1][2]["timeout"] == preflight.SETTINGS["decision_timeout_s"]


def test_preflight_questions_gives_the_decision_bench_the_exact_production_payload(monkeypatch):
    """2026-11-13: Walter Router's decision bench asks the models what production asks (`walter-context
    preflight-questions`), built by this module's own code; a case the rules settle says so."""
    from walter_context.cli import preflight_questions
    monkeypatch.setattr(preflight, "router_tasks", lambda: {"general": "Texte", "coding": "Code"})
    case = {"message": "Écris un script qui surveille le disque", "previous": {"message": "salut", "answer": "Bonjour",
            "age_s": 3600, "thread_id": "t1"}, "candidates": [{"id": "t1", "title": "Entretien du serveur"}]}
    out = preflight_questions(case)
    state, q = preflight.questions(Request(turn_id="bench", message=case["message"],
                                           previous=Exchange(**case["previous"]), candidates=case["candidates"]))
    assert out["state"] == state and out["questions"] == q and out["fast_path"] is None
    assert preflight_questions({"message": "combien font 2+2 ?"})["fast_path"] == "trivial"


MODS = [{"module": "memory", "line": "- **Walter Memory** — la mémoire"},
        {"module": "raw-vault", "line": "- **Raw Vault** — fichiers bruts"}]


def test_question_set_3_asks_l_c_d_and_neither_task_nor_capabilities(monkeypatch):
    """2026-11-14 (owner's L/C/D architecture): set 3 asks the tier, the context plan and which modules' usage guide
    helps; no task family (specialists are the main model's choice) and no capability/delegation question."""
    monkeypatch.setattr(preflight, "router_tasks", lambda: {"general": "G", "coding": "C"})
    req = Request("t", "Analyse ce mail de la banque", previous=prev(),
                  candidates=[{"id": "s1", "title": "Banque", "task": "dossier prêt"}],
                  origin={"channel": "connector", "kind": "email", "source": "gmail", "secret": "x"})
    state, q = preflight.questions_v3(req, MODS)
    assert state["input"] == {"channel": "connector", "kind": "email", "source": "gmail"}
    assert {"handling", "act", "thread", "plan", "extensive", "model_level", "domain", "horizon", "work", "resume",
            "doc_memory", "doc_raw_vault"} == set(q)
    assert "Raw Vault" in q["doc_raw_vault"]["instructions"] and "not an order" in q["doc_raw_vault"]["instructions"]
    _, q2 = preflight.questions(req)
    assert "task" in q2 and "cap_delegation" in q2                       # production (set 2) unchanged


def test_set_3_reading_maps_plans_to_c_levels_with_the_floor():
    a = {"handling": {"choice": "answer", "confidence": 0.9}, "act": {"choice": "continue", "confidence": 0.8},
         "plan": {"choice": "thread", "confidence": 0.6}, "extensive": {"noul": 0.7},
         "model_level": {"choice": "L2", "confidence": 0.7}, "doc_memory": {"noul": 0.8}, "doc_raw_vault": {"noul": 0.2},
         "work": {"noul": 0.6}}
    out = preflight.read_v3(a, Request("t", "x"), MODS)
    assert (out["C"], out["L"], out["docs"], out["work"], out["handling"]) == ("C4", "L2", ["memory"], "yes", "answer")
    assert out["confidence"]["doc_raw_vault"] == 0.8 and "resume" not in out
    near = Request("t", "ok", previous=prev())                       # within the floor window: C0 becomes C1
    assert preflight.context_level("none", None, near) == "C1" and preflight.context_level("none", None) == "C0"
    assert preflight.context_level("thread_and_memory", 0.2) == "C3"

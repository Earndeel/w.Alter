"""DecisionState + reassess + the preflight wiring."""
import sys
import types

import pytest

from walter_context import decision_state as DS
from walter_context import preflight, reassess, state as S
from walter_context.config import STATE_DEFAULTS
from walter_context.preflight import Exchange, Request, run

CFG = {**STATE_DEFAULTS, "coalesce_ms": 10}


def test_observation_versus_inference_and_unknown_stays_unknown():
    w = S.empty("s")
    S.apply(w, [{"kind": "tool.result", "payload": {"tool": "Bash", "summary": "port 443 ouvert"}},
                {"kind": "subagent.reply", "payload": {"subagent_id": "a", "text": "la base est saturée"}},
                {"kind": "memory.changed", "payload": {"items": [{"kind": "decision", "text": "Prestataire A", "ref": "m1"}]}}], CFG)
    ds = DS.build("Alors, où en est-on ?", working=w)
    assert any("port 443" in o["fact"] and o["verification"] == "observed" for o in ds["observations"])
    inf = {i["claim"]: i for i in ds["inferences"]}
    assert inf["la base est saturée"]["verification"] == "reported"          # a sub-agent's word is not an observation
    assert all("la base est saturée" not in o["fact"] for o in ds["observations"])
    assert "Prestataire A" in [d["text"] for d in ds["decisions"]]
    assert any("aucun contexte" in u for u in ds["unknowns"])          # no thread, objective or exchange: said


def test_without_any_context_the_scope_is_explicitly_unknown_and_nothing_is_invented():
    ds = DS.build("Fais le même que tout à l'heure", capabilities=["tools", "memory"])
    assert any("aucun contexte" in u for u in ds["unknowns"])
    assert any("référence du message" in m for m in ds["knowledge"]["missing"])
    assert ds["observations"] == [] and ds["inferences"] == [] and ds["knowledge"]["known"] == []


def test_known_searchable_not_consulted_missing():
    msg = "Tu te souviens de ce qu'on avait décidé ? Et donne-moi le prix actuel du cuivre."
    ds = DS.build(msg, capabilities=["tools", "memory"], prior_decisions=["devis plafonné à 3000 €"])
    k = ds["knowledge"]
    assert any(s.startswith("memory") for s in k["searchable"])               # a source exists, not asked yet
    assert any("web" in m for m in k["missing"])                              # no web capability: said missing
    assert "memory" in k["not_consulted"]
    assert "unknown_needed" in ds["facts"]
    # once memory was consulted in the session the need is known, no longer searchable
    w = S.empty("s")
    S.apply(w, [{"kind": "tool.result", "payload": {"tool": "mcp__walter__memory_recall", "summary": "3 résultats"}}], CFG)
    ds2 = DS.build(msg, capabilities=["tools", "memory"], working=w)
    assert not any(s.startswith("memory") for s in ds2["knowledge"]["searchable"])
    assert any("memory déjà consulté" in s for s in ds2["knowledge"]["known"])


def test_capabilities_not_given_is_an_unknown_not_a_guess():
    ds = DS.build("Regarde le fichier /etc/hosts", use={"message"})
    assert any("non indiquées" in u for u in ds["unknowns"]) and ds["knowledge"]["searchable"] == []


def test_contradictions_constraints_and_staleness_come_from_the_state():
    w = S.empty("s")
    S.apply(w, [{"kind": "observation", "payload": {"text": "port ouvert", "key": "p", "value": "443", "verification": "observed"}},
                {"kind": "observation", "payload": {"text": "port fermé d'après l'agent", "key": "p", "value": "x",
                                                    "verification": "reported"}},
                {"kind": "message.owner", "payload": {"text": "Ne redémarre jamais le service."}},
                {"kind": "observation", "payload": {"text": "ancien relevé", "ttl_s": 1}, "at": "2020-01-01T00:00:00+00:00"}], CFG)
    ds = DS.build("On continue ?", working=w)
    assert ds["contradictions"] and any("Ne redémarre jamais" in c["text"] for c in ds["constraints"])
    assert not any("ancien relevé" in o["fact"] for o in ds["observations"])
    assert any("ancien relevé" in i["claim"] and i["verification"] == "unverified" and "périmé" in i["basis"] for i in ds["inferences"])


def test_use_restricts_inputs_for_the_ablation():
    kw = dict(previous={"message": "m", "answer": "a", "age_s": 60}, objective="finir l'audit", prior_decisions=["d"],
              capabilities=["memory"])
    full = DS.build("ok vas-y", **kw)
    bare = DS.build("ok vas-y", use={"message"}, **kw)
    assert "objective" in full and "last_exchange" in full and full["decisions"]
    assert "objective" not in bare and "last_exchange" not in bare and bare["decisions"] == []
    assert bare["inputs"]["absent"] and bare["inputs"]["used"] == ["message"] and bare["capabilities"] == []


def test_compact_is_bounded():
    w = S.empty("s")
    S.apply(w, [{"kind": "tool.result", "payload": {"tool": "Read", "summary": "x" * 250, "ref": f"r{i}"}} for i in range(60)], CFG)
    ds = DS.build("Que reste-t-il ?" + " détail" * 50, working=w, capabilities=["memory"])
    assert len(str(DS.compact(ds, 1400))) < 2400


# ── reassess ─────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def mgr(tmp_path):
    return S.Manager(S.Store(tmp_path / "w"), dict(CFG))


class Decider:
    def __init__(self):
        self.calls = []

    def __call__(self, state, questions, **kw):
        self.calls.append((state, kw))
        return {"model": "fake/d", "signals": {"context.plan": {"choice": "thread_and_memory"},
                                               "context.needs": {"probabilities": {"memory": 0.8, "web": 0.2}},
                                               "context.extensive": {"noul": 0.7}}}


def test_reassess_asks_only_the_relevant_signals_and_memoises(mgr):
    dec = Decider()
    mgr.update("s", [{"kind": "task.started", "payload": {"task_id": "t", "goal": "migrer"}}])
    body = {"session_id": "s", "trigger": {"kind": "failure", "where": "migrer", "error": "disk full"}}
    out = reassess.reassess(body, decide=dec, mgr=mgr, cfg=dict(CFG))
    assert out["asked"] is True and out["decisions"]["context_level"] == "L3" and out["decisions"]["capabilities"] == ["memory"]
    assert out["decisions"]["extensive"] is True and "Réévaluation (failure)" in out["text"]
    (state, kw), = dec.calls
    assert kw["occasion"] == "turn" and kw["ask"] == ["context.plan", "context.needs", "context.extensive"] and kw["focus"] == "new_message"
    assert kw["samples"] == 1 and "decision_state" in state and "disk full" in state["new_message"]
    again = reassess.reassess(body, decide=dec, mgr=mgr, cfg=dict(CFG))        # same state version + same trigger
    assert again["asked"] is False and again["memoized"] is True and again["decisions"] == out["decisions"] and len(dec.calls) == 1


def test_reassess_says_asked_false_when_nothing_relevant_changed(mgr):
    dec = Decider()
    mgr.update("s", [{"kind": "observation", "payload": {"text": "le build passe"}}])
    cases = [({"kind": "info.arrived", "text": "le build passe"}, "déjà connue"),
             ({"kind": "info.arrived"}, "vide"),
             ({"kind": "interrupted"}, "rien d'ouvert"),
             ({"kind": "memory.contradiction"}, "aucune contradiction"),
             ({"kind": "subagent.alternative"}, "aucune alternative"),
             ({"kind": "objective.changed"}, "aucun objectif"),
             ({"kind": "failure"}, "sans détail"),
             ({"kind": "bogus"}, "inconnu")]
    for tr, why in cases:
        out = reassess.reassess({"session_id": "s", "trigger": tr}, decide=dec, mgr=mgr, cfg=dict(CFG))
        assert out["asked"] is False and why in out["reason"], (tr, out["reason"])
        assert set(out) >= {"asked", "reason", "decision_state", "decisions", "text"}
    assert dec.calls == []


def test_same_failure_is_not_assessed_twice_even_after_the_state_moved(mgr):
    dec = Decider()
    tr = {"kind": "failure", "where": "deploy", "error": "403"}
    assert reassess.reassess({"session_id": "s2", "trigger": tr}, decide=dec, mgr=mgr, cfg=dict(CFG))["asked"]
    mgr.update("s2", [{"kind": "observation", "payload": {"text": "autre chose"}}])
    out = reassess.reassess({"session_id": "s2", "trigger": tr}, decide=dec, mgr=mgr, cfg=dict(CFG))
    assert out["asked"] is False and "déjà évalué" in out["reason"] and len(dec.calls) == 1


def test_interrupted_with_open_work_asks_resume_and_decision_failure_is_said(mgr):
    mgr.update("s3", [{"kind": "task.started", "payload": {"task_id": "t", "goal": "rapport"}}])
    dec = Decider()
    out = reassess.reassess({"session_id": "s3", "trigger": {"kind": "interrupted", "reason": "owner"}}, decide=dec, mgr=mgr, cfg=dict(CFG))
    assert out["asked"] and dec.calls[0][1]["ask"] == ["memory.resume", "context.plan"] and "open_task" in dec.calls[0][1]["facts"]

    def boom(*a, **k):
        raise RuntimeError("no model")
    out = reassess.reassess({"session_id": "s3", "trigger": {"kind": "info.arrived", "text": "nouveau"}}, decide=boom, mgr=mgr, cfg=dict(CFG))
    assert out["asked"] is False and "indisponible" in out["reason"] and out["decisions"] == {}


def test_http_reassess(tmp_path, monkeypatch):
    import json, threading, urllib.request
    from http.server import ThreadingHTTPServer
    from walter_context.preflight import service
    m = S.Manager(S.Store(tmp_path / "w"), dict(CFG))
    monkeypatch.setattr(S, "_MANAGER", [m])
    monkeypatch.setattr(reassess, "_default_decide", Decider())
    srv = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/v1/reassess", method="POST",
                                     data=json.dumps({"session_id": "h", "run_id": "r", "trigger": {"kind": "info.arrived", "text": "Le client a répondu"}}).encode())
        out = json.loads(urllib.request.urlopen(req, timeout=10).read())
        assert out["asked"] is True and out["decisions"]["plan"] == "thread_and_memory"
    finally:
        srv.shutdown()


# ── the preflight wiring ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def fake_decide(monkeypatch):
    calls = []

    def decide(state, questions, **kw):
        calls.append((state, kw))
        sig = {"context.act": {"choice": "continue"}, "context.plan": {"choice": "thread"}, "context.needs": {"probabilities": {}},
               "context.extensive": {"noul": 0.1}, "context.domain": {"choice": "projects"}, "context.horizon": {"choice": "day"},
               "router.tier": {"choice": "L1"}}
        return {"answers": {}, "signals": sig, "model": "fake", "trace": {"registry": "r", "asked": list(sig)}}
    mod = types.ModuleType("walter_memory.llm")
    mod.decide = decide
    pkg = types.ModuleType("walter_memory")
    pkg.llm = mod
    monkeypatch.setitem(sys.modules, "walter_memory", pkg)
    monkeypatch.setitem(sys.modules, "walter_memory.llm", mod)
    monkeypatch.setattr(preflight, "SIGNALS", "registry")
    monkeypatch.setattr(preflight, "READINGS_APART", False)
    monkeypatch.setattr(preflight, "decision_chain", lambda: ("fake",))
    monkeypatch.setattr(preflight, "owner_today", lambda: "2026-11-17")
    return calls


def _switch(monkeypatch, **kw):
    monkeypatch.setattr(preflight, "state_settings", lambda path=None: {**STATE_DEFAULTS, **kw})


def test_preflight_unchanged_with_the_switches_off(fake_decide, monkeypatch):
    p = run(Request("t", "Et pour le budget ?", candidates=[{"id": "th", "title": "Devis"}]))
    state, kw = fake_decide[0]
    assert "decision_state" not in state and kw["facts"] == ["threads"] and "decision_state" not in p.decision


def test_preflight_facts_and_summary_come_from_the_decision_state_when_on(fake_decide, monkeypatch, tmp_path):
    _switch(monkeypatch, decision_state=True)
    cands = [{"id": "th", "title": "Devis", "objective": "boucler le devis", "task": "relancer"}]
    p = run(Request("t", "Tu te souviens de ce qu'on avait décidé ?", candidates=cands,
                    previous=Exchange("et le devis ?", "en attente", 300, "th")))
    state, kw = fake_decide[0]
    assert state["decision_state"]["objective"] == "boucler le devis" and "open_task" in kw["facts"] and "threads" in kw["facts"]
    # the turn reads DS.TURN_INPUTS: no capability list (ablation 17/11), so no « a source could answer » fact
    assert "unknown_needed" not in kw["facts"] and "capabilities" not in p.decision["decision_state"]["inputs"]
    assert p.decision["decision_state"]["searchable"] == 0 and p.decision["decision_state"]["working_state"] is False
    assert p.to_dict()["decision"]["decision_state"]                    # the ContextPlan carries it


def test_preflight_reads_the_living_state_only_with_its_switch(fake_decide, monkeypatch, tmp_path):
    m = S.Manager(S.Store(tmp_path / "w"), dict(CFG))
    m.update("sess", [{"kind": "message.owner", "payload": {"text": "Ne touche jamais à la prod."}},
                      {"kind": "tool.result", "payload": {"tool": "Bash", "summary": "déploiement bloqué"}}])
    monkeypatch.setattr(S, "_MANAGER", [m])
    _switch(monkeypatch, decision_state=True, living_state=False)
    run(Request("t", "On reprend ?", session_id="sess"))
    assert "constraints" not in fake_decide[-1][0]["decision_state"]
    _switch(monkeypatch, decision_state=True, living_state=True)
    p = run(Request("t2", "On reprend ?", session_id="sess"))
    ds = fake_decide[-1][0]["decision_state"]
    assert any("Ne touche jamais à la prod" in c for c in ds["constraints"]) and any("déploiement bloqué" in o for o in ds["observed"])
    assert p.decision["decision_state"]["working_state"] is True

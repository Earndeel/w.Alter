"""Module guardians (2026-10-30): the supervisor hands incidents to the guardian first; the shared engine acts only
through declared, level-capped, allow-listed actions and tells the owner only when needed. No model, no Telegram."""
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

from test_guardians import G, _decl

SRC = Path(__file__).resolve().parent.parent / "bin" / "walter-guardian"
loader = importlib.machinery.SourceFileLoader("walter_guardian", str(SRC))
spec = importlib.util.spec_from_loader("walter_guardian", loader)
A = importlib.util.module_from_spec(spec); loader.exec_module(A)


import pytest


@pytest.fixture(autouse=True)
def _no_real_repair_agent(monkeypatch):
    """No test starts a transient unit or reaches the engine: the repair agent is faked where a test needs it."""
    monkeypatch.setattr(A, "launch_repair", lambda module, incident, tried: False)
    monkeypatch.setattr(A, "delegate", lambda *a, **k: {"ok": False, "error": "no engine in tests"})


def _incident(key="service:x", kind="service_down", severity="high", **ev):
    return {"version": 1, "module": "a", "key": key, "kind": kind, "severity": severity, "summary": "x en panne",
            "evidence": ev}


# ---- supervisor ---------------------------------------------------------------------------------------------------

def _guarded(tmp_path, monkeypatch, verdicts, severity="high"):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path / "inst"))
    tmp_path.mkdir(parents=True, exist_ok=True)
    sent = []
    monkeypatch.setattr(G, "_telegram", lambda text: sent.append(text) or True)
    d = _decl(tmp_path, "a", json.dumps([_incident(severity=severity)]))
    d["guardian"] = ["fake"]
    monkeypatch.setattr(G, "declarations", lambda: [d])
    calls = []
    monkeypatch.setattr(G, "_run_guardian", lambda cmd, inc: calls.append(inc) or {"verdicts": verdicts})
    return sent, calls


def test_fixed_or_expected_incident_is_never_told(tmp_path, monkeypatch):
    for outcome in ("fixed", "expected", "pending"):
        sent, calls = _guarded(tmp_path / outcome, monkeypatch, {"a:service:x": {"outcome": outcome}})
        r = G.check(notify=True)
        assert calls and r["guardians"] == {"a:service:x": outcome} and sent == []


def test_needs_owner_is_told_with_the_guardians_words(tmp_path, monkeypatch):
    sent, _ = _guarded(tmp_path, monkeypatch, {"a:service:x": {"outcome": "needs_owner",
                                                               "message_fr": "Le crédit est épuisé, il faut recharger."}})
    G.check(notify=True)
    assert len(sent) == 1 and "recharger" in sent[0] and "x en panne" not in sent[0]


def test_no_verdict_waits_a_grace_then_tells(tmp_path, monkeypatch):
    sent, calls = _guarded(tmp_path, monkeypatch, {})
    G.check(notify=True)
    assert sent == []                                                     # guardian silent: grace first
    p = tmp_path / "inst/state/guardians/state.json"
    st = json.loads(p.read_text())
    st["open"]["a:service:x"]["first_seen"] = "2000-01-01T00:00:00+00:00"
    p.write_text(json.dumps(st))
    G.check(notify=True)
    assert len(sent) == 1                                                 # never silence


def test_critical_is_told_at_once_and_self_guarded_module_is_left_to_itself(tmp_path, monkeypatch):
    sent, _ = _guarded(tmp_path, monkeypatch, {"a:service:x": {"outcome": "expected"}}, severity="critical")
    G.check(notify=True)
    assert len(sent) == 1
    sent2 = []
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path / "self"))
    monkeypatch.setattr(G, "_telegram", lambda text: sent2.append(text) or True)
    d = _decl(tmp_path, "s", json.dumps([{**_incident(), "module": "s"}]))
    d["guardian"] = "self"
    monkeypatch.setattr(G, "declarations", lambda: [d])
    G.check(notify=True)
    assert sent2 == []


# ---- engine -----------------------------------------------------------------------------------------------------

def _module(tmp_path, check_items, actions=None, max_level="G1", fallback=None):
    root = tmp_path / "mod"
    (root / "contracts").mkdir(parents=True)
    (root / "guardian").mkdir()
    flag = tmp_path / "touched-ok"
    check = tmp_path / "check.py"
    check.write_text("import json,os,sys\n"
                     f"print('[]' if os.path.exists({str(flag)!r}) else {json.dumps(check_items)!r})\n")
    (root / "contracts" / "maintenance.json").write_text(json.dumps(
        {"version": 1, "module": "a", "check": [sys.executable, str(check)], "max_level": max_level}))
    acts = actions if actions is not None else {
        "restart_unit": {"level": "G1", "command": ["touch", str(tmp_path) + "/touched-{unit}"], "params": {"unit": ["ok", "x"]}},
        "dangerous": {"level": "G2", "command": ["touch", str(tmp_path / "g2")]}}
    (root / "guardian" / "playbook.json").write_text(json.dumps(
        {"version": 1, "module": "a", "notes": ["n"], "evidence": {"service_down": [["echo", "{unit}"]]},
         "actions": acts, "fallback": fallback or {}, "settle_seconds": 0}))
    return root, flag


def test_engine_acts_within_gates_and_verifies(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path / "inst"))
    inc = _incident(unit="ok")
    root, flag = _module(tmp_path, [inc])
    monkeypatch.setattr(A, "ask_model", lambda prompt: ({"incidents": [{"key": "a:service:x", "outcome": "act",
        "actions": [{"id": "dangerous"}, {"id": "restart_unit", "params": {"unit": "; rm -rf /"}},
                    {"id": "restart_unit", "params": {"unit": "ok"}}]}]}, {"route": "fake"}))
    out = A.run("a", [inc], root=root)
    v = out["verdicts"]["a:service:x"]
    assert v["outcome"] == "fixed" and flag.exists()
    assert not (tmp_path / "g2").exists()                                 # above max_level: refused
    assert [a.get("refused") for a in v["actions"]] == ["not_allowed", "param_unit", None]


def test_engine_gives_up_to_the_owner_after_its_rounds(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path / "inst"))
    inc = _incident(unit="x")
    root, flag = _module(tmp_path, [inc])
    answer = ({"incidents": [{"key": "a:service:x", "outcome": "act",
                              "actions": [{"id": "restart_unit", "params": {"unit": "x"}}]}]}, {})
    monkeypatch.setattr(A, "ask_model", lambda prompt: answer)
    outcomes = [A.run("a", [inc], root=root)["verdicts"]["a:service:x"]["outcome"] for _ in range(3)]
    assert outcomes == ["failed", "failed", "needs_owner"]                # the check never clears: tell, with what was tried
    assert "restart_unit" in A.run("a", [inc], root=root)["verdicts"]["a:service:x"]["message_fr"]


def test_engine_without_model_uses_the_playbook_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path / "inst"))
    inc = _incident(unit="ok")
    root, flag = _module(tmp_path, [inc], fallback={"service_down": {"action": "restart_unit", "params": {"unit": "unit"}}})
    monkeypatch.setattr(A, "ask_model", lambda prompt: (None, {"error": "URLError"}))
    v = A.run("a", [inc], root=root)["verdicts"]["a:service:x"]
    assert v["outcome"] == "fixed" and v["by"] == "fallback"
    other = _incident(key="health:y", kind="health_problem")
    assert A.run("a", [other], root=root)["verdicts"]["a:health:y"]["outcome"] == "unknown"


def test_engine_masks_secrets_and_rejects_bad_playbooks(tmp_path):
    assert "abc" not in A.mask("Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123")
    assert "hunter2xx" not in A.mask("password=hunter2xx")
    root, _ = _module(tmp_path, [], actions={"x": {"level": "G1", "command": ["systemctl", "restart", "{unit}"]}})
    try:
        A.load("a", root)
        raise AssertionError("an action parameter without an allow-list must be refused")
    except ValueError:
        pass


# ---- repair agent (2026-11-20) -----------------------------------------------------------------------------------

def test_what_would_reach_the_owner_goes_to_the_repair_agent_first(tmp_path, monkeypatch):
    """Monsieur, 2026-11-20: the guardian fixes it the way he would from Claude Code; he hears only its verdict."""
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path / "inst"))
    inc = _incident(unit="x")
    root, flag = _module(tmp_path, [inc])
    monkeypatch.setattr(A, "ask_model", lambda prompt: ({"incidents": [{"key": "a:service:x", "outcome": "needs_owner",
                                                                         "message_fr": "Je ne sais pas."}]}, {}))
    started = []
    monkeypatch.setattr(A, "launch_repair", lambda m, i, tried: started.append(i["key"]) or True)
    v = A.run("a", [inc], root=root)["verdicts"]["a:service:x"]
    assert v["outcome"] == "pending" and v["repair"] == "started" and started == ["service:x"]

    asked = []
    def fake_delegate(module, goal, key, budget=A.REPAIR_BUDGET):
        asked.append((module, goal))
        flag.write_text("")                                            # the agent fixed it
        return {"ok": True, "output": 'Cause trouvée. {"outcome": "fixed", "cause": "unité mal nommée", '
                                      '"summary_fr": "Le service était mal configuré ; corrigé.", "commit": "abc"}'}
    monkeypatch.setattr(A, "delegate", fake_delegate)
    out = A.repair("a", inc, "", root=root)
    assert out["verdict"]["outcome"] == "fixed" and out["poste"] == "coding/L3"
    assert "service:x" in asked[0][1] and "Claude Code" in asked[0][1] and "commite seulement TES fichiers" in asked[0][1]
    assert A.module_check(A.load("a", root)[0]) == set()                 # the module's own check confirms it


def test_the_owner_hears_the_repair_agents_words_and_only_after_its_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path / "inst"))
    inc = _incident(unit="x")
    v0 = {"outcome": "failed", "diagnosis_fr": "", "message_fr": ""}
    path = A._repair_file("a", "a:service:x")
    def runs(*verdicts, ago=7200):
        now = A.time.time()
        path.write_text(json.dumps({"runs": [{"t": now - ago - 10 * n, "verdict": v} for n, v in enumerate(verdicts)]}))
    runs({"outcome": "needs_owner", "summary_fr": "Le crédit Venice est épuisé.", "question_fr": "Le recharger ?"})
    v = A.escalate("a", inc, v0)
    assert v["outcome"] == "needs_owner" and "Venice" in v["message_fr"] and "recharger" in v["message_fr"]
    runs({"outcome": "external", "cause": "HTTP 503"})
    assert A.escalate("a", inc, v0)["outcome"] == "external"
    runs({"outcome": "failed", "cause": "x"}, ago=600)                    # a run 10 min ago: wait before the next
    assert A.escalate("a", inc, v0)["repair"] == "waiting"
    runs({"outcome": "fixed", "summary_fr": "Corrigé."}, {"outcome": "failed", "cause": "x"})
    v = A.escalate("a", inc, v0)                                         # two runs and still there: the owner
    assert v["outcome"] == "needs_owner" and "2 fois" in v["message_fr"]
    path.write_text(json.dumps({"runs": [], "running": {"since": A.time.time(), "pid": A.os.getpid()}}))
    assert A.escalate("a", inc, v0)["repair"] == "running"

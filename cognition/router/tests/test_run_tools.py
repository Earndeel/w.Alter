"""P1 (2026-10-27): walter_run works with Walter's capabilities, research has a route, observations are persisted by
the Router. The tools themselves are the engine's (SOCLE A6, 2026-11-11: the Router's own loop, its native file tools
and its trace builder were removed). No model, no database, no gateway process here."""
import json

from walter_router.serve import engine, run


def test_default_toolsets_are_walter_capabilities_and_no_switch_restores_the_terminal(monkeypatch):
    assert run.default_toolsets() == ["walter-web", "skills", "memory"]
    monkeypatch.setenv("WALTER_RUN_TOOLS", "legacy")                  # the former switch has no effect any more
    assert run.default_toolsets() == ["walter-web", "skills", "memory"]


def test_research_goes_to_a_general_sub_agent_with_the_web(monkeypatch):
    seen = []

    def fake_decide(conn, spec):
        seen.append(spec)
        if spec.get("task") == "general":
            return {"task": "general", "model_id": "m", "execution": [{"provider": "p", "model": "m"}]}
        return {"task": "research", "mode": "tool", "tool": "research"}
    monkeypatch.setattr(run, "decide", fake_decide)
    captured = {}
    monkeypatch.setattr(engine, "enabled", lambda d: True)
    monkeypatch.setattr(engine, "run_text", lambda d, spec, **k: captured.update(d=d, spec=spec) or {"ok": True})
    monkeypatch.setattr(run, "choose", type("C", (), {}))
    conn = type("Conn", (), {"execute": lambda self, *a: type("R", (), {"fetchone": lambda s: {"interface": "text"}})()})()
    assert run._run(conn, {"goal": "prix du café", "task": "research"})["ok"]
    assert captured["d"]["requested_task"] == "research" and captured["d"]["task"] == "general"
    assert captured["spec"]["toolsets"] == ["walter-web", "skills"] and seen[-1]["level"] == "L2"


def test_persist_observations_reads_fenced_json_and_passes_run_task_geo(monkeypatch):
    sent = {}
    monkeypatch.setattr(run, "_memory", lambda action, payload: sent.update(action=action, **payload) or {"stored": 1})
    out = '```json\n{"observations": [{"subject": "x", "source_url": "https://a"}]}\n```'
    assert run._persist_observations(out, "r1", "t1", {"pays": "TH"}) == {"stored": 1}
    assert sent["action"] == "observations-add" and sent["run_id"] == "r1" and sent["geo"] == {"pays": "TH"}
    assert run._persist_observations("pas du JSON", "r1", "t1", None)["stored"] == 0
    assert "observations" in run._persist_observations('{"offers": []}', "r1", "t1", None)["errors"][0]["error"]

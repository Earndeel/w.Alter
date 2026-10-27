"""P1 (2026-10-27): walter_run works with Walter's capabilities through the Tool Gateway, research has a route,
the sub-agent's trace is shaped for walter_logs. No model, no database, no gateway process here."""
import json

from walter_router.serve import run, text_agent


def test_default_toolsets_are_walter_capabilities_and_legacy_switch(monkeypatch):
    monkeypatch.delenv("WALTER_RUN_TOOLS", raising=False)
    assert run.default_toolsets() == ["walter-web", "skills", "memory"]
    assert "terminal" not in run.default_toolsets()
    monkeypatch.setenv("WALTER_RUN_TOOLS", "legacy")
    assert run.default_toolsets() == ["web", "walter-web", "file", "terminal"]


def test_toolsets_map_to_gateway_tools_only_for_walter_capabilities():
    walter = sorted({t for ts in ["walter-web", "skills", "memory"] for t in run.TOOLSET_TOOLS.get(ts, [])})
    assert walter == ["memory_context", "memory_events", "memory_search", "skill_read", "skills_search", "walter_browse"]
    assert not text_agent.tools_for(["walter-web", "skills", "memory"])      # no native shell or file tool
    assert {t["function"]["name"] for t in text_agent.tools_for(["terminal", "file"])} == {"terminal", "read_file", "write_file"}


def test_research_goes_to_a_general_sub_agent_with_the_web(monkeypatch):
    seen = []

    def fake_decide(conn, spec):
        seen.append(spec)
        if spec.get("task") == "general":
            return {"task": "general", "model_id": "m", "execution": [{"provider": "p", "model": "m"}]}
        return {"task": "research", "mode": "tool", "tool": "research"}
    monkeypatch.setattr(run, "decide", fake_decide)
    captured = {}
    monkeypatch.setattr(run, "_text", lambda conn, d, spec: captured.update(d=d, spec=spec) or {"ok": True})
    monkeypatch.setattr(run, "choose", type("C", (), {}))
    conn = type("Conn", (), {"execute": lambda self, *a: type("R", (), {"fetchone": lambda s: {"interface": "text"}})()})()
    assert run._run(conn, {"goal": "prix du café", "task": "research"})["ok"]
    assert captured["d"]["requested_task"] == "research" and captured["d"]["task"] == "general"
    assert captured["spec"]["toolsets"] == ["walter-web", "skills"] and seen[-1]["level"] == "L2"


def test_trace_events_are_walter_logs_vocabulary():
    result = {"ok": True, "output": "3 offres", "tools": [{"name": "walter_browse", "arguments": {"query": "q"},
                                                           "result": {"success": True}, "ok": True, "at": 1.0}]}
    evs = run._events("goal", "", result, "m")
    assert [e["type"] for e in evs] == ["user/message", "tool/call", "tool/result", "assistant/message"]
    assert evs[1]["tool"] == "walter_browse" and json.loads(evs[1]["text"]) == {"query": "q"}
    assert all(e.get("at") for e in evs)

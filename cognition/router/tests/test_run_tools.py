"""P1 (2026-10-27): walter_run works with Walter's capabilities through the Tool Gateway, research has a route,
the sub-agent's trace is shaped for walter_logs. No model, no database, no gateway process here."""
import json

from walter_router.serve import run, text_agent


def test_default_toolsets_are_walter_capabilities_and_no_switch_restores_the_terminal(monkeypatch):
    assert run.default_toolsets() == ["walter-web", "skills", "memory"]
    monkeypatch.setenv("WALTER_RUN_TOOLS", "legacy")                  # the former switch has no effect any more
    assert run.default_toolsets() == ["walter-web", "skills", "memory"]


def test_unsandboxed_terminal_is_gone_and_refused(tmp_path):
    """Security 2026-11-09: no native shell tool exists, whatever the toolsets or the environment."""
    import inspect, pytest
    assert "shell=True" not in inspect.getsource(text_agent) and "Popen(args" not in inspect.getsource(text_agent)
    for ts in (["terminal"], ["code_execution"], ["file", "terminal"]):
        with pytest.raises(ValueError):
            text_agent.tools_for(ts)
        assert run._text(None, {"execution": []}, {"goal": "g", "toolsets": ts})["error"] == "toolset_disabled"
    with pytest.raises(ValueError):
        text_agent.execute_tool("terminal", {"command": "id"}, 5, tmp_path)


def test_file_tools_stay_inside_the_run_workspace(tmp_path):
    ws = tmp_path / "ws"; ws.mkdir()
    (tmp_path / "secret").write_text("x")
    assert text_agent.execute_tool("write_file", {"path": "a/b.txt", "content": "ok"}, 5, ws)["ok"]
    assert text_agent.execute_tool("read_file", {"path": "a/b.txt"}, 5, ws)["content"] == "ok"
    for bad in ("../secret", str(tmp_path / "secret"), "/etc/passwd", "a/../../secret"):
        for name, args in (("read_file", {"path": bad}), ("write_file", {"path": bad, "content": "x"})):
            with __import__("pytest").raises(RuntimeError, match="path_outside_workspace"):
                text_agent.execute_tool(name, args, 5, ws)
    (ws / "link").symlink_to(tmp_path / "secret")
    with __import__("pytest").raises(RuntimeError, match="path_outside_workspace"):
        text_agent.execute_tool("read_file", {"path": "link"}, 5, ws)


def test_toolsets_map_to_gateway_tools_only_for_walter_capabilities():
    walter = sorted({t for ts in ["walter-web", "skills", "memory"] for t in run.TOOLSET_TOOLS.get(ts, [])})
    assert walter == ["memory_context", "memory_events", "memory_search", "skill_read", "skills_search", "walter_browse"]
    assert not text_agent.tools_for(["walter-web", "skills", "memory"])      # no native shell or file tool
    assert {t["function"]["name"] for t in text_agent.tools_for(["file"])} == {"read_file", "write_file"}


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


def test_child_context_is_optional_and_the_pack_is_traced(monkeypatch):
    monkeypatch.setattr(run.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("absent")))
    assert run._child_context({"goal": "g"}) == {}                       # walter-context missing: caller's context
    evs = run._events("g", "pack", {"ok": True, "output": "x"}, "m", {"tokens": 10, "blocks": []})
    assert evs[0]["type"] == "system/context" and evs[1]["type"] == "user/message"


def test_persist_observations_reads_fenced_json_and_passes_run_task_geo(monkeypatch):
    sent = {}
    monkeypatch.setattr(run, "_memory", lambda action, payload: sent.update(action=action, **payload) or {"stored": 1})
    out = '```json\n{"observations": [{"subject": "x", "source_url": "https://a"}]}\n```'
    assert run._persist_observations(out, "r1", "t1", {"pays": "TH"}) == {"stored": 1}
    assert sent["action"] == "observations-add" and sent["run_id"] == "r1" and sent["geo"] == {"pays": "TH"}
    assert run._persist_observations("pas du JSON", "r1", "t1", None)["stored"] == 0
    assert "observations" in run._persist_observations('{"offers": []}', "r1", "t1", None)["errors"][0]["error"]

"""Regression: the reported provider must be the one that actually answered, on the same model."""
from __future__ import annotations

import ast
import os
import asyncio
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from walter_router.serve import run, text_agent


@pytest.fixture
def execution(monkeypatch):
    rows = []
    # Native-loop tests do not contact the active Tool Gateway, Context or Memory.
    monkeypatch.setattr(run, "default_toolsets", lambda: [])
    monkeypatch.setenv("WALTER_RUN_CONTEXT", "caller")
    monkeypatch.delenv("WALTER_RUN_ID", raising=False)
    monkeypatch.delenv("WALTER_TASK_ID", raising=False)
    monkeypatch.setattr(run.execution, "log", lambda conn, row: rows.append(row))
    return SimpleNamespace(conn=SimpleNamespace(commit=lambda: None), logs=rows)


def decision():
    return {"task": "coding", "model_id": "claude-opus-5-5", "execution": [
        {"provider": "kie", "model": "claude-opus-5-5"},
        {"provider": "openrouter", "model": "anthropic/claude-opus-5.5"},
        # A stale decision must never introduce another model.
        {"provider": "codex", "model": "gpt-6.1-sol", "fallback_for": "claude-opus-5-5"}]}


def answer(route, content="OK", **extra):
    return {"ok": True, "provider": route["provider"], "model": route["model"],
            "response_model": route["model"], "response_id": "response-test",
            "message": {"role": "assistant", "content": content}, **extra}


def test_provider_failure_tries_same_model_and_requires_user_notice(monkeypatch, execution):
    seen = []
    def complete(route, messages, tools, timeout):
        seen.append(route["provider"])
        if route["provider"] == "kie":
            raise RuntimeError("empty_provider_response")
        return answer(route)
    monkeypatch.setattr(text_agent, "complete", complete)
    out = run._text(execution.conn, decision(), {"goal": "test"})
    assert out["ok"] and seen == ["kie", "openrouter"]
    assert out["routed"]["provider"] == "openrouter"
    assert out["routed"]["model_id"] == "claude-opus-5-5"
    assert out["user_notification_required"] and "même modèle" in out["user_notice"]
    assert out["notices"][0]["from_provider"] == "kie"
    assert out["notices"][0]["to_provider"] == "openrouter"
    assert [(r["provider"], r["ok"]) for r in execution.logs] == [("kie", False), ("openrouter", True)]


def test_exhaustion_never_uses_subscription_or_another_model(monkeypatch, execution):
    seen = []
    def fail(route, *args):
        seen.append(route["provider"])
        raise RuntimeError("provider_timeout")
    monkeypatch.setattr(text_agent, "complete", fail)
    out = run._text(execution.conn, decision(), {"goal": "test"})
    assert not out["ok"] and seen == ["kie", "openrouter"]
    assert out["error"] == "all_providers_failed" and out["routed"]["provider"] is None
    assert out["user_notification_required"] and "Aucun autre modèle" in out["user_notice"]


def test_every_provider_is_tried_without_a_three_attempt_cutoff(monkeypatch, execution):
    d = decision()
    d["execution"] = [{"provider": str(i), "model": "same-model"} for i in range(4)]
    def complete(route, *args):
        if route["provider"] != "3":
            raise RuntimeError("unavailable")
        return answer(route)
    monkeypatch.setattr(text_agent, "complete", complete)
    out = run._text(execution.conn, d, {"goal": "test"})
    assert out["ok"] and len(out["routed"]["attempts"]) == 4


def test_tool_history_survives_failover_and_tools_are_not_repeated(monkeypatch, execution, tmp_path):
    calls = []
    def complete(route, messages, tools, timeout):
        calls.append(route["provider"])
        if len(calls) == 1:
            return answer(route, None, message={"role": "assistant", "tool_calls": [
                {"id": "write-once", "type": "function", "function": {"name": "write_file",
                 "arguments": __import__("json").dumps({"path": "once.txt", "content": "x"})}}]})
        assert messages[-1]["role"] == "tool" and messages[-1]["tool_call_id"] == "write-once"
        if route["provider"] == "kie":
            raise RuntimeError("provider_timeout")
        return answer(route)
    monkeypatch.setattr(text_agent, "complete", complete)
    out = run._text(execution.conn, decision(), {"goal": "test", "toolsets": ["file"]})
    assert out["ok"] and calls == ["kie", "kie", "openrouter"]
    assert len(out["tools"]) == 1 and out["tools"][0]["name"] == "write_file" and out["tools"][0]["ok"]
    assert open(out["tools"][0]["result"]["path"]).read() == "x"


def test_success_without_failover_does_not_emit_a_warning(monkeypatch, execution):
    monkeypatch.setattr(text_agent, "complete", lambda route, *args: answer(route))
    out = run._text(execution.conn, decision(), {"goal": "test"})
    assert out["ok"] and not out["user_notification_required"] and not out["notices"]


@pytest.mark.parametrize("cost,status", [(0.125, "reported"), (0.07, "estimated"), (0, "reported"),
                                       (None, "unknown")])
def test_response_telemetry_reaches_attempt_and_execution_log(monkeypatch, execution, cost, status):
    telemetry = {"usage": {"prompt_tokens": 41, "completion_tokens": 17, "total_tokens": 58},
                 "cost_usd": cost, "cost_status": status}
    monkeypatch.setattr(text_agent, "complete", lambda route, *args: answer(route, **telemetry))
    out = run._text(execution.conn, decision(), {"goal": "test"})
    assert out["ok"]
    for row in (out["routed"]["attempts"][0], execution.logs[0]):
        assert {key: row[key] for key in telemetry} == telemetry


def test_unmeasured_and_failed_attempts_keep_unknown_telemetry(monkeypatch, execution):
    def complete(route, *args):
        if route["provider"] == "kie":
            raise RuntimeError("provider_timeout")
        return answer(route)  # an older gateway can omit telemetry entirely
    monkeypatch.setattr(text_agent, "complete", complete)
    out = run._text(execution.conn, decision(), {"goal": "test"})
    assert out["ok"] and [row["ok"] for row in execution.logs] == [False, True]
    for row in out["routed"]["attempts"] + execution.logs:
        assert {key: row[key] for key in ("usage", "cost_usd", "cost_status")} == {
            "usage": None, "cost_usd": None, "cost_status": "unknown"}


def test_each_tool_turn_keeps_its_own_telemetry(monkeypatch, execution, tmp_path):
    calls = []
    def complete(route, *args):
        calls.append(route["provider"])
        telemetry = {"usage": {"total_tokens": len(calls) * 10},
                     "cost_usd": len(calls) / 100, "cost_status": "reported"}
        if len(calls) == 1:
            return answer(route, None, **telemetry, message={"role": "assistant", "tool_calls": [
                {"id": "measured-tool", "type": "function", "function": {"name": "write_file",
                 "arguments": __import__("json").dumps({"path": "measured.txt", "content": "x"})}}]})
        return answer(route, **telemetry)
    monkeypatch.setattr(text_agent, "complete", complete)
    out = run._text(execution.conn, decision(), {"goal": "test", "toolsets": ["file"]})
    assert out["ok"] and open(out["tools"][0]["result"]["path"]).read() == "x" and len(calls) == 2
    for rows in (out["routed"]["attempts"], execution.logs):
        assert [(row["usage"]["total_tokens"], row["cost_usd"], row["cost_status"]) for row in rows] == [
            (10, 0.01, "reported"), (20, 0.02, "reported")]


def test_a_hanging_provider_leaves_time_for_its_fallback(monkeypatch, execution):
    clock, limits = [100.0], []
    monkeypatch.setattr(run.time, "monotonic", lambda: clock[0])
    def complete(route, messages, tools, timeout):
        limits.append(timeout)
        if route["provider"] == "kie":
            clock[0] += timeout
            raise RuntimeError("provider_timeout")
        return answer(route)
    monkeypatch.setattr(text_agent, "complete", complete)
    out = run._text(execution.conn, decision(), {"goal": "test", "budget_seconds": 90})
    assert out["ok"] and limits == [45, 45]


def test_routes_do_not_add_an_automatic_fallback_model(monkeypatch):
    from walter_router.serve import routes
    conn = SimpleNamespace(execute=lambda *a: SimpleNamespace(fetchone=lambda: {
        "interface": "chat", "requirements": {}, "modes": []}))
    model = decision()["model_id"]
    monkeypatch.setattr(routes.execution, "routes", lambda conn, mid, *a, **k: [
        {"provider": "openrouter", "model": "anthropic/claude-opus-5.5"}])
    out = routes.with_execution(conn, {"task": "coding", "model_id": model})
    assert len(out["execution"]) == 1 and not any(r.get("fallback_for") for r in out["execution"])


def test_toolsets_and_turn_limits_are_enforced():
    assert text_agent.tools_for([]) == []
    assert text_agent.tools_for(["web"]) == []  # no terminal authority granted by a web-only request
    response = {"message": {"role": "assistant", "tool_calls": [{"id": "x", "function": {
        "name": "terminal", "arguments": '{"command":"touch /must-not-be-created"}'}}]}}
    out = text_agent.run("test", "", [], 1, time.monotonic() + 10, lambda *a: response)
    assert not out["ok"] and out["error"] == "max_turns_exhausted"
    assert out["tools"][0]["name"] == "terminal" and not out["tools"][0]["ok"]


def test_transport_has_no_agent_runtime_and_checks_gateway_attribution(monkeypatch):
    import json
    seen = {}
    def fake(cmd, **kwargs):
        seen.update(cmd=cmd, spec=json.loads(kwargs["input"]))
        return SimpleNamespace(returncode=0, stdout=json.dumps({"ok": True, "provider": "codex", "model": "other"}))
    monkeypatch.setattr(text_agent.subprocess, "run", fake)
    with pytest.raises(RuntimeError, match="gateway_route_mismatch"):
        text_agent.complete(decision()["execution"][0], [], [], 5)
    assert seen["cmd"] == ["walter-llm", "call"]


def test_timeout_is_reported_as_a_provider_failure(monkeypatch):
    def timeout(*a, **k):
        raise subprocess.TimeoutExpired("gateway", 1)
    monkeypatch.setattr(text_agent.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="provider_timeout"):
        text_agent.complete(decision()["execution"][0], [], [], 1)


def _gateway_function():
    # Load the pure transport function without starting FastAPI, a vault or background warm-up.
    from walter_router import paths
    tree = ast.parse((paths.ROOT / "llm" / "gateway.py").read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name in {"exact_call", "provider_completion"}]
    ns = {"litellm_target": lambda route: {"model": route["model"], "api_key": "test-key"},
          "_usage": lambda response: {}, "_telemetry": lambda response: {
              "usage": {}, "cost_usd": None, "cost_status": "unknown"},
          "_install_codex_auth": lambda: None, "os": os, "PAID": {"kie", "openrouter", "arnict"},
          "test_gate": lambda route, spec: None, "_charge": lambda *a: None}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "gateway.py", "exec"), ns)
    return ns["exact_call"]


@pytest.mark.parametrize("kind", ["success", "wrong_model", "empty", "incomplete", "exception"])
def test_exact_transport_never_retries_or_accepts_a_substitute(monkeypatch, kind):
    seen = []
    message = {"role": "assistant", "content": "" if kind == "empty" else "OK"}
    async def completion(**kwargs):
        seen.append(kwargs)
        if kind == "exception":
            raise RuntimeError("credentials and private body must not leak")
        return SimpleNamespace(id="response-test", model="gpt-other" if kind == "wrong_model" else "claude-opus-5.5",
                               choices=[SimpleNamespace(message=SimpleNamespace(model_dump=lambda **k: message),
                                                        finish_reason="length" if kind == "incomplete" else "stop")])
    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    result = asyncio.run(_gateway_function()({"route": decision()["execution"][0], "messages": [], "tools": []}))
    assert len(seen) == 1 and seen[0]["num_retries"] == 0 and seen[0]["fallbacks"] == []
    assert result["ok"] == (kind == "success")
    assert "credentials" not in str(result)


def unrestricted_decision():
    return {"task": "general", "model_id": "m-a", "require": "unrestricted", "execution": [
        {"provider": "venice", "model": "m-a-venice"}]}


def favourites(monkeypatch):
    from walter_router.analysis import knowledge
    monkeypatch.setattr(knowledge, "load", lambda: {"unrestricted_favourites": [
        {"model_id": "m-a"}, {"model_id": "m-b"}]})
    monkeypatch.setattr(run.execution, "routes", lambda conn, mid, variant="", **k: [
        {"provider": "arnict", "model": f"{mid}-arnict", "model_id": mid, "probe_ok": True}])


def test_declared_fallback_model_runs_after_every_provider_of_the_titular(monkeypatch, execution):
    favourites(monkeypatch)
    seen = []
    def complete(route, messages, tools, timeout):
        seen.append((route["model_id"], route["provider"]))
        if route["model_id"] == "m-a":
            raise RuntimeError("provider_timeout")
        return answer(route)
    monkeypatch.setattr(text_agent, "complete", complete)
    out = run._text(execution.conn, unrestricted_decision(), {"goal": "test"})
    assert out["ok"] and seen == [("m-a", "venice"), ("m-b", "arnict")]
    assert out["routed"]["executed_model_id"] == "m-b" and out["routed"]["model_id"] == "m-a"
    assert [n["type"] for n in out["notices"]] == ["model_fallback"] and out["user_notification_required"]
    assert [(r["model_id"], r["ok"]) for r in execution.logs] == [("m-a", False), ("m-b", True)]


def test_no_model_substitution_when_the_request_is_not_declared_as_unrestricted(monkeypatch, execution):
    favourites(monkeypatch)
    seen = []
    def fail(route, *args):
        seen.append(route["model_id"])
        raise RuntimeError("provider_timeout")
    monkeypatch.setattr(text_agent, "complete", fail)
    d = {**unrestricted_decision(), "require": None}
    out = run._text(execution.conn, d, {"goal": "test"})
    assert not out["ok"] and seen == ["m-a"] and "Aucun autre modèle" in out["user_notice"]

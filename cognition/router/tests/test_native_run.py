"""The gateway's exact transport (`walter-llm call`) and the Router's routes. The Router's own text loop (and its
failover tests) was removed with SOCLE A6 (2026-11-11): text jobs run in Walter Engine only."""
from __future__ import annotations

import ast
import os
import asyncio
import sys
from types import SimpleNamespace

import pytest

from walter_router.serve import run


def decision():
    return {"task": "coding", "model_id": "claude-opus-5-5", "execution": [
        {"provider": "kie", "model": "claude-opus-5-5"},
        {"provider": "openrouter", "model": "anthropic/claude-opus-5.5"},
        # A stale decision must never introduce another model.
        {"provider": "codex", "model": "gpt-6.1-sol", "fallback_for": "claude-opus-5-5"}]}


def test_routes_do_not_add_an_automatic_fallback_model(monkeypatch):
    from walter_router.serve import routes
    conn = SimpleNamespace(execute=lambda *a: SimpleNamespace(fetchone=lambda: {
        "interface": "chat", "requirements": {}, "modes": []}))
    model = decision()["model_id"]
    monkeypatch.setattr(routes.execution, "routes", lambda conn, mid, *a, **k: [
        {"provider": "openrouter", "model": "anthropic/claude-opus-5.5"}])
    out = routes.with_execution(conn, {"task": "coding", "model_id": model})
    assert len(out["execution"]) == 1 and not any(r.get("fallback_for") for r in out["execution"])


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


def test_without_the_engine_a_text_job_fails_explicitly_and_no_router_loop_exists(monkeypatch):
    """SOCLE A6: binding `legacy` (or none) is no longer a second agent loop: the job is refused, said to the user."""
    import importlib.util
    monkeypatch.setenv("WALTER_RUN_ENGINE", "legacy")
    conn = SimpleNamespace(execute=lambda *a: SimpleNamespace(fetchone=lambda: {"interface": "text"}))
    out = run._dispatch(conn, decision(), {"goal": "Résume X"})
    assert not out["ok"] and out["error"] == "engine_unavailable" and out["reason"] == "engine_not_bound"
    assert out["user_notification_required"] and "indisponible" in out["user_notice"]
    assert not hasattr(run, "_text") and importlib.util.find_spec("walter_router.serve.text_agent") is None

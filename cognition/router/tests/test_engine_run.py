"""Lot E5 (2026-11-10): walter_run text jobs are executed by Walter Engine (Engine API `delegate`), not a second loop."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from walter_router.serve import engine, run, text_agent


@pytest.fixture
def api(tmp_path, monkeypatch):
    seen: list = []
    reply = {"status": 200, "body": {"ok": True, "output": "résultat", "status": "ok", "reason": "completed",
                                     "tools": ["mcp__walter__memory_search"], "session_id": "mcp/walter_run/task-x",
                                     "walter_session": "dsh/vm/abc", "request_id": "k", "resumed": False}}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append({"auth": self.headers.get("Authorization"), "body": body})
            data = json.dumps(reply["body"]).encode()
            self.send_response(reply["status"]); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tok = tmp_path / "api.token"; tok.write_text("t0ken\n")
    monkeypatch.setenv("WALTER_RUN_ENGINE", "engine")
    monkeypatch.setenv("WALTER_ENGINE_API_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("WALTER_ENGINE_API_TOKEN_FILE", str(tok))
    monkeypatch.setenv("WALTER_RUN_ID", "run-parent")
    monkeypatch.setenv("WALTER_SESSION_ID", "claude_code/sess")
    monkeypatch.delenv("WALTER_DELEGATION_DEPTH", raising=False)
    memory: list = []
    monkeypatch.setattr(run, "_memory", lambda action, payload: memory.append((action, payload)) or {})
    monkeypatch.setattr(text_agent, "run", lambda *a, **k: pytest.fail("the Router's own loop must not run"))
    yield SimpleNamespace(seen=seen, reply=reply, memory=memory)
    srv.shutdown()


def decision(**extra):
    return {"task": "general", "model_id": "some-model", "execution": [{"provider": "p", "model": "m"}], **extra}


class Conn:
    def execute(self, *a):
        return SimpleNamespace(fetchone=lambda: {"interface": "text"})

    def commit(self):
        pass


def test_text_job_is_one_delegation_to_the_engine_filed_under_the_callers_run(api):
    out = run._dispatch(Conn(), decision(), {"goal": "Résume X", "context": "faits", "budget_seconds": 120,
                                             "constraints": {"lang": "fr"}})
    assert out["ok"] and out["output"] == "résultat" and out["runtime"] == "walter-engine"
    assert out["trace_session"] == "dsh/vm/abc" and out["tools"] == [{"name": "mcp__walter__memory_search"}]
    (call,) = api.seen
    assert call["auth"] == "Bearer t0ken"                       # token in the header, never in the URL
    d = call["body"]["delegation"]
    assert call["body"]["op"] == "delegate" and call["body"]["caller"] == "walter_run"
    assert d["goal"] == "Résume X" and d["context"] == "faits" and d["task"] == "general" and d["budget_seconds"] == 120
    assert d["parent"] == {"run_id": "run-parent", "session_id": "claude_code/sess", "task_id": out["task_id"], "depth": 0}
    assert len(d["idempotency_key"]) >= 8
    actions = [a for a, _ in api.memory]
    assert actions == ["task-start", "link", "task-end"]
    end = api.memory[-1][1]
    assert end["status"] == "ended" and end["events"] == [] and end["session_id"] == "dsh/vm/abc"
    assert end["routing"]["provider"] == "walter-engine"


def test_router_task_names_map_to_engine_postes_and_unknown_ones_are_auto(api):
    assert engine.engine_task({"task": "code"}, {}) == "coding"
    assert engine.engine_task({"task": "summarization"}, {}) == "summarization"
    assert engine.engine_task({"task": "research"}, {}) == "auto"


def test_a_named_model_stays_on_the_exact_model_path(api, monkeypatch):
    assert not engine.enabled(decision(source="named"))
    assert engine.enabled(decision())
    monkeypatch.setenv("WALTER_RUN_ENGINE", "legacy")
    assert not engine.enabled(decision())


def test_engine_refusal_and_cancel_are_reported_never_retried_elsewhere(api):
    api.reply.update(status=403, body={"error": "max_depth", "message": "delegation depth 3 reaches the limit 3"})
    out = run._dispatch(Conn(), decision(), {"goal": "x"})
    assert not out["ok"] and out["error"] == "max_depth" and out["user_notification_required"]
    api.reply.update(status=200, body={"ok": False, "output": "", "status": "cancelled", "reason": "budget_seconds",
                                       "tools": [], "walter_session": "dsh/vm/c"})
    out = run._dispatch(Conn(), decision(), {"goal": "x"})
    assert not out["ok"] and out["error"] == "budget_seconds" and api.memory[-1][1]["status"] == "cancelled"


def test_engine_down_is_said_and_no_second_loop_runs(api, monkeypatch):
    monkeypatch.setenv("WALTER_ENGINE_API_URL", "http://127.0.0.1:9")
    out = run._dispatch(Conn(), decision(), {"goal": "x"})
    assert not out["ok"] and out["error"] == "engine_unavailable" and "indisponible" in out["user_notice"]


def test_observations_are_persisted_by_the_router_from_the_engines_answer(api, monkeypatch):
    api.reply["body"]["output"] = '{"observations": [{"subject": "s", "source": "u"}]}'
    got = {}
    monkeypatch.setattr(run, "_persist_observations", lambda out, r, t, g: got.update(out=out, run=r) or {"stored": 1})
    out = run._dispatch(Conn(), decision(), {"goal": "x", "persist": "observations"})
    assert out["persisted"] == {"stored": 1} and got["run"] == "run-parent"

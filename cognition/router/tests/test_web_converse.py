"""Router rule for conversational web services (gateway /v1/web/converse), offline: Browse is stubbed."""
import ast
import json
import sys
import time
from pathlib import Path


def _ns(tmp_path, services, calls, logs):
    source = Path(__file__).resolve().parents[1] / "llm" / "gateway.py"
    tree = ast.parse(source.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"web_services", "web_converse"}]
    conf = tmp_path / "gateway.json"
    conf.write_text(json.dumps({"web_services": services}))

    def converse(host, capability, message, **kw):
        calls.append((host, capability, message, kw))
        return {"ok": True, "status": "done", "reply": "réponse", "request_id": kw.get("request_id"),
                "conversation": kw.get("conversation"), "mode": "replay", "timings": {"total_ms": 50.0}}
    ns = {"json": json, "time": time, "sys": sys, "_CONF_PATH": conf, "_WEB": {"mtime": None, "services": {}},
          "_browse_converse": lambda: converse, "log": logs.append}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
    return ns, conf


SERVICES = {"_doc": "x", "chatgpt": {"enabled": False, "host": "chatgpt.com", "note": "pending"},
            "fixture": {"enabled": True, "host": "127.0.0.1:1", "capability": "chat", "session": "s1",
                        "start_url": "http://127.0.0.1:1/"}}


def test_unknown_and_disabled_services_never_reach_browse(tmp_path):
    calls, logs = [], []
    ns, _ = _ns(tmp_path, SERVICES, calls, logs)
    code, out = ns["web_converse"]("hermes", {"service": "nope", "message": "x"})
    assert code == 404 and out["services"] == ["chatgpt", "fixture"]
    code, out = ns["web_converse"]("hermes", {"service": "chatgpt", "message": "x"})
    assert code == 403 and out["error"] == "service_disabled" and out["note"] == "pending"
    assert calls == [] and logs == []


def test_rule_routes_to_the_recipe_and_logs_metadata_only(tmp_path):
    calls, logs = [], []
    ns, _ = _ns(tmp_path, SERVICES, calls, logs)
    code, out = ns["web_converse"]("hermes", {"service": "fixture", "message": "secret words",
                                              "conversation": "telegram:1", "request_id": "telegram:1:42"})
    assert code == 200 and out["reply"] == "réponse"
    host, cap, msg, kw = calls[0]
    assert (host, cap, msg) == ("127.0.0.1:1", "chat", "secret words")
    assert kw["session"] == "s1" and kw["request_id"] == "telegram:1:42" and kw["conversation"] == "telegram:1"
    assert out["route"] == {"rule": "web_services.fixture", "transport": "browser", "recipe": "127.0.0.1:1/chat"}
    assert "router_ms" in out["timings"]
    entry = logs[0]
    assert entry["kind"] == "web" and entry["provider"] == "web:fixture" and entry["ok"] is True
    assert "secret words" not in json.dumps(entry) and "réponse" not in json.dumps(entry)


def test_table_is_reread_when_the_config_changes(tmp_path):
    calls, logs = [], []
    ns, conf = _ns(tmp_path, SERVICES, calls, logs)
    assert ns["web_converse"]("hermes", {"service": "chatgpt", "message": "x"})[0] == 403
    enabled = json.loads(json.dumps(SERVICES))
    enabled["chatgpt"]["enabled"] = True
    time.sleep(0.01)
    conf.write_text(json.dumps({"web_services": enabled}))
    import os
    os.utime(conf, (time.time() + 1, time.time() + 1))
    assert ns["web_converse"]("hermes", {"service": "chatgpt", "message": "x"})[0] == 200


def test_message_bounds(tmp_path):
    ns, _ = _ns(tmp_path, SERVICES, [], [])
    assert ns["web_converse"]("hermes", {"service": "fixture", "message": "  "})[0] == 400
    assert ns["web_converse"]("hermes", {"service": "fixture", "message": "x" * 20001})[0] == 400

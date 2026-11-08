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
        files = [(Path(p).name, Path(p).read_bytes(), Path(p)) for p in kw.get("files") or []]
        calls.append((host, capability, message, {**kw, "files": files}))
        produced = tmp_path / "produced.png"
        produced.write_bytes(b"\x89PNG fake")
        return {"ok": True, "status": "done", "reply": "réponse", "request_id": kw.get("request_id"),
                "conversation": kw.get("conversation"), "mode": "replay", "timings": {"total_ms": 50.0},
                "files": [{"kind": "image", "name": "image-1.png", "path": str(produced), "mime": "image/png", "bytes": 10}]
                if "image" in message else []}
    ns = {"json": json, "time": time, "sys": sys, "Path": Path, "_CONF_PATH": conf, "_WEB": {"mtime": None, "services": {}},
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


def test_model_and_files_in_and_out(tmp_path):
    import base64
    calls, logs = [], []
    ns, _ = _ns(tmp_path, SERVICES, calls, logs)
    code, out = ns["web_converse"]("hermes", {"service": "fixture", "message": "fais une image", "model": "GPT-6 high",
                                              "files": [{"name": "../../etc/note.txt", "data": base64.b64encode(b"ORANGE").decode()}]})
    assert code == 200
    _, _, _, kw = calls[0]
    assert kw["model"] == "GPT-6 high"
    (name, data, path), = kw["files"]
    assert (name, data) == ("note.txt", b"ORANGE") and not path.exists()     # temp copy removed after the exchange
    f, = out["files"]
    assert "path" not in f and base64.b64decode(f["data"]) == b"\x89PNG fake"
    assert logs[0]["files_in"] == 1 and logs[0]["files_out"] == 1 and "ORANGE" not in json.dumps(logs[0])
    code, out = ns["web_converse"]("hermes", {"service": "fixture", "message": "x"})
    assert calls[-1][3]["model"] is None and calls[-1][3]["files"] == []      # default: the service's own model


def test_bad_attachment_is_refused_before_browse(tmp_path):
    calls, logs = [], []
    ns, _ = _ns(tmp_path, SERVICES, calls, logs)
    code, out = ns["web_converse"]("hermes", {"service": "fixture", "message": "x", "files": [{"name": "a", "data": "@@"}]})
    assert code == 400 and calls == []

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


def test_default_service_is_the_only_enabled_one(tmp_path):
    calls, logs = [], []
    ns, _ = _ns(tmp_path, SERVICES, calls, logs)
    code, out = ns["web_converse"]("router", {"message": "bonjour"})
    assert code == 200 and out["service"] == "fixture" and calls[0][0] == "127.0.0.1:1"
    two = {**SERVICES, "other": {"enabled": True, "host": "x"}}
    ns, _ = _ns(tmp_path, two, calls, logs)
    code, out = ns["web_converse"]("router", {"message": "bonjour"})
    assert code == 400 and out["error"] == "service required" and sorted(out["services"]) == ["fixture", "other"]


def test_router_tool_sends_local_files_and_returns_local_paths(tmp_path, monkeypatch):
    """walter_web (walter-router web): paths in, base64 only between router and gateway, paths out (0600)."""
    import base64
    import subprocess
    from walter_router.serve import web
    sent = {}

    def fake_run(cmd, input, **kw):
        assert cmd == ["walter-llm", "web"]
        sent.update(json.loads(input))
        out = {"ok": True, "reply": "ok", "service": "chatgpt", "request_id": "r1",
               "files": [{"kind": "image", "name": "../image 1.png", "mime": "image/png", "bytes": 4,
                          "data": base64.b64encode(b"\x89PNG").decode()}]}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(out), "")
    monkeypatch.setattr(web.subprocess, "run", fake_run)
    monkeypatch.setattr(web, "out_dir", lambda: tmp_path / "out")
    doc = tmp_path / "note.txt"
    doc.write_text("ORANGE-42")
    out = web.converse({"message": "lis", "files": [str(doc)], "model": "high", "conversation": "c1"})
    assert sent["files"] == [{"name": "note.txt", "data": base64.b64encode(b"ORANGE-42").decode()}]
    assert sent["model"] == "high" and sent["conversation"] == "c1" and "service" not in sent
    path = Path(out["files"][0]["path"])
    assert path.read_bytes() == b"\x89PNG" and path.parent.parent == tmp_path / "out" and path.name == "image 1.png"
    assert oct(path.stat().st_mode & 0o777) == "0o600" and "data" not in out["files"][0]


def test_router_tool_refuses_bad_input_before_the_gateway(tmp_path, monkeypatch):
    from walter_router.serve import web
    monkeypatch.setattr(web.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    assert web.converse({"message": ""})["error"] == "message required"
    assert "file not found" in web.converse({"message": "x", "files": [str(tmp_path / "absent")]})["error"]
    assert "unknown fields" in web.converse({"message": "x", "provider": "y"})["error"]
    assert "at most 10" in web.converse({"message": "x", "files": ["a"] * 11})["error"]

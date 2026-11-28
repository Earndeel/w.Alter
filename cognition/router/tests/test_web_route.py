"""The owner's rule gives some classified intents to a web chat service; on failure, the usual path with a notice."""
from walter_router.analysis import knowledge
from walter_router.serve import run, web

RULES = {"web_services": {"_doc": "x", "chatgpt": {"tasks": {"weather": None, "calculation": None, "research": ["L1"]}}}}


class Conn:
    def commit(self):
        pass


def test_rule_matches_task_and_level_of_an_enabled_service_only(monkeypatch):
    monkeypatch.setattr(knowledge, "load", lambda: RULES)
    monkeypatch.setattr(web, "_enabled", lambda: {"chatgpt"})
    assert web.route_for("weather", "L2")["service"] == "chatgpt"
    assert web.route_for("calculation", None)["conversation"] == web.DEFAULT_CONVERSATION
    assert web.route_for("research", "L1")["service"] == "chatgpt"
    assert web.route_for("research", "L3") is None and web.route_for("general", "L1") is None
    monkeypatch.setattr(web, "_enabled", lambda: set())
    assert web.route_for("weather", "L1") is None          # the gateway's switch wins


def _decision(monkeypatch):
    d = {"task": "research", "mode": "web", "intent": {"level": "L1"},
         "web": {"service": "chatgpt", "conversation": "walter-router", "fallback_mode": "tool", "why": "règle"}}
    monkeypatch.setattr(run, "decide", lambda conn, spec: d)
    monkeypatch.setattr(run.execution, "log", lambda conn, entry: 1)


def test_web_answer_is_returned_verbatim(monkeypatch):
    _decision(monkeypatch)
    sent = {}
    monkeypatch.setattr(web, "converse", lambda spec: sent.update(spec) or {"ok": True, "reply": "75 828 $", "files": [],
                                                                            "conversation": "walter-router"})
    monkeypatch.setattr(run, "_dispatch", lambda *a: (_ for _ in ()).throw(AssertionError("usual path used")))
    out = run.run(Conn(), {"request": "prix du bitcoin"})
    assert out["ok"] and out["kind"] == "web" and out["output"] == "75 828 $"
    assert out["routed"]["provider"] == "web:chatgpt" and not out["user_notification_required"]
    assert sent["message"] == "prix du bitcoin" and sent["service"] == "chatgpt" and sent["conversation"] == "walter-router"


def test_web_failure_takes_the_usual_path_and_says_so(monkeypatch):
    _decision(monkeypatch)
    monkeypatch.setattr(web, "converse", lambda spec: {"ok": False, "status": "failed", "error": "tab_gone"})
    seen = {}

    def dispatch(conn, d, spec):
        seen.update(mode=d["mode"], goal=spec["goal"])
        return {"ok": True, "output": "réponse habituelle", "notices": [], "user_notice": "",
                "user_notification_required": False}
    monkeypatch.setattr(run, "_dispatch", dispatch)
    out = run.run(Conn(), {"request": "prix du bitcoin"})
    assert seen == {"mode": "tool", "goal": "prix du bitcoin"}
    assert out["ok"] and out["output"] == "réponse habituelle" and out["user_notification_required"]
    assert out["notices"][0]["type"] == "web_fallback" and "tab_gone" in out["user_notice"]


def test_chat_commands_come_from_the_gateways_rule_table(monkeypatch, tmp_path):
    import json
    cfg = tmp_path / "gateway.json"
    cfg.write_text(json.dumps({"web_services": {"_doc": "x", "chatgpt": {"enabled": True},
                                                "claude": {"command": "cl", "enabled": False}}}))
    monkeypatch.setattr(web.instance, "_walter", lambda *a: str(cfg))
    assert web.commands() == {"gpt": "chatgpt", "cl": "claude"}
    monkeypatch.setattr(web.instance, "_walter", lambda *a: str(tmp_path / "absent.json"))
    assert web.commands() == {}

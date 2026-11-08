"""Run with the Hermes venv: venv/bin/python -m pytest -q ~/.hermes/plugins/walter-router/test_walter_router.py"""
import asyncio
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("walter_router_plugin", Path(__file__).with_name("__init__.py"))
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


def test_tools_hidden_inside_a_routed_child(monkeypatch):
    monkeypatch.setenv(plugin.CHILD_ENV, "1")
    assert plugin._available() is False


def test_route_answers_with_model_and_execution_routes():
    d = json.loads(asyncio.run(plugin._handle_route({"task": "general", "request": "analyse", "level": "L1"})))
    assert d["model_id"] and d["execution"][0]["provider"]


def test_run_never_substitutes_a_named_model():
    d = json.loads(asyncio.run(plugin._handle_run({"request": "x", "goal": "x", "model": "gpt-6-1-sol",
                                                    "provider": "arnict"})))
    assert d["ok"] is False and "arnict" in d["error"]


def test_named_model_route_keeps_its_provider():
    d = json.loads(asyncio.run(plugin._handle_route({"request": "x", "model": "claude-opus-5-5", "provider": "kie"})))
    assert d["model_id"] == "claude-opus-5-5" and {e["provider"] for e in d["execution"]} == {"kie"}


def test_unknown_task_is_an_error_not_a_crash():
    assert "error" in json.loads(asyncio.run(plugin._handle_route({"task": "nope", "request": "x"})))


def test_route_without_task_uses_the_classifier():
    d = json.loads(asyncio.run(plugin._handle_route({"request": "Une vidéo TikTok d'une cliente qui donne son avis face caméra"})))
    assert d.get("intent", {}).get("task") == "text_to_video" and d["role"] == "ugc"


def test_verdict_and_feedback_tools_report_errors_cleanly():
    assert "error" in json.loads(asyncio.run(plugin._handle_verdict({"alert_id": 999999999, "decision": "adopter"})))
    assert "error" in json.loads(asyncio.run(plugin._handle_feedback({"rating": 9})))


def _telegram_wiring(monkeypatch, sent_by):
    import pytest
    pytest.importorskip("telegram.ext")                 # Hermes venv only
    from types import SimpleNamespace
    monkeypatch.setattr(plugin, "_web_commands", lambda: {"gpt": "chatgpt"})
    monkeypatch.setattr(plugin, "_home_chat", lambda: "42")
    exchanges, tasks, handlers, extras = [], [], [], []

    async def fake_exchange(service, text, chat_id, message_id, sent_at, reply, **kw):
        exchanges.append((service, text, chat_id, message_id))
        extras.append(kw)
    monkeypatch.setattr(plugin, "web_exchange", fake_exchange)
    app = SimpleNamespace(add_handler=lambda h, group=0: handlers.append((h, group)),
                          create_task=lambda coro: tasks.append(coro))
    plugin._wire_web_commands(app, None)
    handler, group = handlers[0]
    replies = []

    async def reply_text(text, **kw):
        replies.append(text)

    async def chat_action(*a):
        pass
    msg = SimpleNamespace(text="/gpt Bonjour\nligne 2", chat=SimpleNamespace(id=int(sent_by)), message_id=7,
                          date=None, reply_text=reply_text, photo=None, document=None, caption=None)
    update = SimpleNamespace(effective_message=msg, effective_user=SimpleNamespace(id=int(sent_by)))
    context = SimpleNamespace(bot=SimpleNamespace(send_chat_action=chat_action))
    _telegram_wiring.last = SimpleNamespace(handlers=handlers, extras=extras, msg=msg)
    return handler, group, update, context, tasks, exchanges


def test_web_command_owner_message_bypasses_the_agent(monkeypatch):
    handler, group, update, context, tasks, exchanges = _telegram_wiring(monkeypatch, "42")
    assert group == -1 and "gpt" in handler.commands
    from telegram.ext import ApplicationHandlerStop
    try:
        asyncio.run(handler.callback(update, context))
        raise AssertionError("the agent loop would also get the message")
    except ApplicationHandlerStop:
        pass
    asyncio.run(tasks[0])
    assert exchanges == [("chatgpt", "Bonjour\nligne 2", 42, 7)]


def test_web_command_ignores_anyone_but_the_owner(monkeypatch):
    handler, group, update, context, tasks, exchanges = _telegram_wiring(monkeypatch, "99")
    asyncio.run(handler.callback(update, context))      # returns: Hermes applies its own rules
    assert tasks == [] and exchanges == []


def test_reply_chunks_fit_telegram():
    parts = plugin._chunks("a" * 9000)
    assert [len(p) for p in parts] == [4000, 4000, 1000]


def test_web_command_model_prefix_and_caption_attachment(monkeypatch):
    from types import SimpleNamespace
    handler, group, update, context, tasks, exchanges = _telegram_wiring(monkeypatch, "42")
    from telegram.ext import ApplicationHandlerStop
    w = _telegram_wiring.last
    caption_handler, caption_group = w.handlers[1]
    assert caption_group == -1
    msg = w.msg
    msg.text = "/gpt [GPT-6 high] Que vois-tu ?"
    try:
        asyncio.run(handler.callback(update, context))
    except ApplicationHandlerStop:
        pass
    asyncio.run(tasks[-1])
    assert exchanges[-1][1] == "Que vois-tu ?" and w.extras[-1]["model"] == "GPT-6 high" and w.extras[-1]["files"] is None

    async def get_file():
        async def download_as_bytearray():
            return bytearray(b"JPEGDATA")
        return SimpleNamespace(download_as_bytearray=download_as_bytearray)
    msg.text, msg.caption = None, "/gpt Décris la photo"
    msg.photo = [SimpleNamespace(get_file=None), SimpleNamespace(get_file=get_file)]   # largest last
    try:
        asyncio.run(caption_handler.callback(update, context))
    except ApplicationHandlerStop:
        pass
    asyncio.run(tasks[-1])
    assert exchanges[-1][1] == "Décris la photo" and w.extras[-1]["model"] is None
    assert w.extras[-1]["files"] == [("photo-7.jpg", b"JPEGDATA")]


def test_web_exchange_sends_produced_files(monkeypatch):
    import base64
    monkeypatch.setattr(plugin, "_post_web", lambda body, timeout: {
        "ok": True, "status": "done", "reply": "", "timings": {},
        "files": [{"kind": "image", "name": "image-1.png", "mime": "image/png", "data": base64.b64encode(b"PNG").decode()},
                  {"kind": "file", "name": "x.csv", "error": "no_download"}]})
    texts, sent = [], []

    async def reply(t):
        texts.append(t)

    async def send_file(name, mime, data, kind):
        sent.append((name, mime, data, kind))
    m = asyncio.run(plugin.web_exchange("chatgpt", "image", 1, 2, None, reply, send_file=send_file))
    assert sent == [("image-1.png", "image/png", b"PNG", "image")]
    assert texts == ["⚠️ non récupéré : x.csv"] and m["files_out"] == 1


def test_web_tool_is_registered_and_returns_the_router_json_even_on_failure():
    """walter_web: the real router CLI; an unknown service is refused before any browser action, JSON kept."""
    names = []

    class Ctx:
        def register_tool(self, **kw):
            names.append(kw["name"])
    plugin.register(Ctx())
    assert "walter_web" in names and "message" in plugin.WEB_SCHEMA["parameters"]["required"]
    d = json.loads(asyncio.run(plugin._handle_web({"message": "x", "service": "nope", "model": ""})))
    assert d["ok"] is False and d["error"] == "unknown_service" and d["services"]

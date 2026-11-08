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
    exchanges, tasks, handlers = [], [], []

    async def fake_exchange(service, text, chat_id, message_id, sent_at, reply):
        exchanges.append((service, text, chat_id, message_id))
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
                          date=None, reply_text=reply_text)
    update = SimpleNamespace(effective_message=msg, effective_user=SimpleNamespace(id=int(sent_by)))
    context = SimpleNamespace(bot=SimpleNamespace(send_chat_action=chat_action))
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

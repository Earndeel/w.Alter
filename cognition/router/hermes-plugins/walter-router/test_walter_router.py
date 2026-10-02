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
    assert d["model_id"] and d["execution"][0]["hermes_provider"]


def test_run_refuses_media_and_returns_the_decision():
    d = json.loads(asyncio.run(plugin._handle_run({"task": "text_to_video", "request": "pub cinématique",
                                                    "goal": "x"})))
    assert "media" in d["error"] and d["decision"]["model_id"] == "seedance-2-5"


def test_unknown_task_is_an_error_not_a_crash():
    assert "error" in json.loads(asyncio.run(plugin._handle_route({"task": "nope", "request": "x"})))


def test_route_without_task_uses_the_classifier():
    d = json.loads(asyncio.run(plugin._handle_route({"request": "Une vidéo TikTok d'une cliente qui donne son avis face caméra"})))
    assert d.get("intent", {}).get("task") == "text_to_video" and d["role"] == "ugc"


def test_verdict_and_feedback_tools_report_errors_cleanly():
    assert "error" in json.loads(asyncio.run(plugin._handle_verdict({"alert_id": 999999999, "decision": "adopter"})))
    assert "error" in json.loads(asyncio.run(plugin._handle_feedback({"rating": 9})))

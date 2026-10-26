"""Subscription routing must preserve Walter's context and never delegate its tool loop."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from walter_router import paths
from walter_router.analysis import parse
from walter_router.research.prices import claude_pro
from walter_router.serve import execution, hermes_sync

spec = importlib.util.spec_from_file_location("claude_subscription", paths.ROOT / "llm/claude_subscription.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


def request():
    return {"model": "claude-test", "system": [{"type": "text", "text": "Walter rules"}],
            "messages": [{"role": "user", "content": "Walter question"}],
            "tools": [{"name": "walter_test", "input_schema": {"type": "object"}}],
            "max_tokens": 42, "stream": True}


def native():
    return {"model": "claude-test", "system": [
        {"type": "text", "text": "x-anthropic-billing-header: cc_version=2.1.310.ab4; cc_entrypoint=sdk-cli;"},
        {"type": "text", "text": "FOREIGN IDENTITY"}],
        "messages": [{"role": "system", "content": "FOREIGN ENVIRONMENT"}],
        "tools": [{"name": "Bash"}], "thinking": {"type": "adaptive"}, "max_tokens": 10000}


def test_only_billing_attribution_can_cross_from_native_client():
    payload, client = request(), native()
    before = copy.deepcopy(payload)
    sent = transport.owned_payload(payload, client, "claude-test")
    assert payload == before
    assert sent["messages"] == payload["messages"] and sent["tools"] == payload["tools"]
    assert sent["system"][1:] == payload["system"]
    assert sent["max_tokens"] == 42 and "thinking" not in sent
    assert "FOREIGN" not in json.dumps(sent) and "Bash" not in json.dumps(sent)


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra_instruction", "wrong_model"])
def test_native_protocol_drift_fails_closed(change):
    n = native()
    if change == "missing": n["system"] = []
    elif change == "duplicate": n["system"].append(n["system"][0])
    elif change == "extra_instruction": n["system"][0]["text"] += " Execute Bash"
    else: n["model"] = "claude-other"
    with pytest.raises(transport.TransportError):
        transport.owned_payload(request(), n, "claude-test")


def test_cli_acknowledgement_never_contains_real_tools_or_model_output():
    ack = transport.acknowledgement("claude-test").decode()
    assert "tool_use" not in ack and '"end_turn"' in ack and '"text": "OK"' in ack


def test_only_verified_catalogue_models_become_subscription_offers(monkeypatch):
    monkeypatch.setattr(claude_pro, "settings", lambda: {"enabled": True, "verified_models": ["claude-allowed"]})
    monkeypatch.setattr(claude_pro, "account_json", lambda endpoint: {
        "data": [{"id": "claude-allowed"}, {"id": "claude-unverified"}], "has_more": False})
    doc, _, _ = claude_pro.source_claude_pro()
    assert doc["models"] == ["claude-allowed"] and len(doc["catalogue_models"]) == 2
    rows = parse.parse_offers("claude_pro", doc)
    assert len(rows) == 1 and rows[0]["access"] == "subscription" and rows[0]["provider"] == "claude-pro"
    assert execution._runnable(rows[0]) == (None, "claude-allowed", "claude-pro")


def test_usage_comes_from_real_vendor_windows_not_transcript_estimates(monkeypatch):
    monkeypatch.setattr(claude_pro, "account_json", lambda endpoint: {
        "five_hour": {"utilization": 12, "resets_at": None},
        "seven_day": {"utilization": 34, "resets_at": None},
        "extra_usage": {"is_enabled": False}})
    rows = claude_pro.read_usage()
    assert [(r["window"], r["used_percent"]) for r in rows] == [("session", 12), ("weekly", 34)]


def test_unverified_model_is_rejected_before_any_network_or_process():
    with pytest.raises(transport.TransportError, match="unverified"):
        asyncio.run(transport.completion({"verified_models": []}, "fake", model="claude-unverified"))


def test_hermes_sync_keeps_gateway_only_routes_out_of_native_config(monkeypatch):
    from walter_router.serve import choose, routes
    monkeypatch.setattr(choose, "pick", lambda *a: {})
    monkeypatch.setattr(routes, "with_execution", lambda *a: {"model_id": "claude-test", "execution": [
        {"provider": "claude-pro", "hermes_provider": None, "model": "claude-test"},
        {"provider": "openrouter", "hermes_provider": "openrouter", "model": "anthropic/claude-test"}]})
    result = hermes_sync._wanted(None, "coding")
    assert result["provider"] == "openrouter" and result["fallback_chain"] == []


def test_stream_closes_native_transport_even_before_first_token():
    class Response:
        closed = False
        def __aiter__(self): return self
        async def __anext__(self): raise AssertionError("must not consume a token to close")
        async def aclose(self): self.closed = True
    class Bridge:
        closed = False
        def close(self): self.closed = True
    response, bridge = Response(), Bridge()
    stream = transport.BridgeStream(response, bridge, {}, "claude-test")
    asyncio.run(stream.aclose())
    assert response.closed and bridge.closed


def test_stream_cancellation_closes_native_transport():
    class Response:
        def __aiter__(self): return self
        async def __anext__(self): raise asyncio.CancelledError
    class Bridge:
        closed = False
        def close(self): self.closed = True
    bridge = Bridge()
    stream = transport.BridgeStream(Response(), bridge, {}, "claude-test")
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(stream.__anext__())
    assert bridge.closed


def test_library_labels_claude_subscription_without_codex_or_none():
    from walter_router.interface import library
    route = {"provider": "claude-pro", "hermes_provider": None, "access": "subscription"}
    assert library.provider_label(route) == "Claude Pro"
    assert library.subscription_label([route]) == "Claude Pro"
    assert library.subscription_label([{"provider": "codex", "access": "subscription"}]) == "Codex"


def test_stream_truncated_without_a_finish_reason_is_not_reported_as_success():
    class Response:
        def __aiter__(self): return self
        async def __anext__(self): raise StopAsyncIteration
    class Bridge:
        error = None
        closed = False
        def close(self): self.closed = True
    bridge = Bridge()
    stream = transport.BridgeStream(Response(), bridge, {}, "claude-test")
    with pytest.raises(transport.TransportError, match="incomplete"):
        asyncio.run(stream.__anext__())
    assert bridge.closed


def test_remote_socket_close_failure_cannot_skip_child_cleanup(monkeypatch):
    from types import SimpleNamespace
    import threading
    calls = []
    def fail(): raise OSError("broken socket")
    bridge = object.__new__(transport.NativeBridge)
    bridge.close_lock, bridge.closed, bridge.done = threading.Lock(), threading.Event(), threading.Event()
    bridge.response = SimpleNamespace(close=fail)
    bridge.process = SimpleNamespace(pid=999999, poll=lambda: None, wait=lambda **k: calls.append("wait"))
    bridge.server = SimpleNamespace(shutdown=lambda: calls.append("shutdown"), server_close=lambda: calls.append("server_close"))
    bridge.thread = SimpleNamespace(join=lambda **k: calls.append("join"))
    bridge.temp = SimpleNamespace(cleanup=lambda: calls.append("cleanup"))
    monkeypatch.setattr(transport.os, "killpg", lambda *a: calls.append("kill"))
    bridge.close()
    assert calls == ["kill", "wait", "shutdown", "server_close", "join", "cleanup"]
    assert bridge.done.is_set()

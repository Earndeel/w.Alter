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
    monkeypatch.setattr(claude_pro, "account_json", lambda endpoint, account=None: {
        "data": [{"id": "claude-allowed"}, {"id": "claude-unverified"}], "has_more": False})
    doc, _, _ = claude_pro.source_claude_pro()
    assert doc["models"] == ["claude-allowed"] and len(doc["catalogue_models"]) == 2
    rows = parse.parse_offers("claude_pro", doc)
    assert len(rows) == 1 and rows[0]["access"] == "subscription" and rows[0]["provider"] == "claude-pro"
    assert execution._runnable(rows[0]) == (None, "claude-allowed", "claude-pro")


def test_usage_comes_from_real_vendor_windows_not_transcript_estimates(monkeypatch):
    monkeypatch.setattr(claude_pro, "account_json", lambda endpoint, account=None: {
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


def test_each_claude_account_is_its_own_route_in_declaration_order(monkeypatch):
    """2026-11-07: the second account goes first once the first one's week is nearly spent, still before paid routes."""
    from walter_router.store import db
    def accounts(spent):
        return lambda c: {"claude-pro": [{"sub_id": "anthropic-pro", "plan": "Claude Pro", "used_percent": spent},
                                         {"sub_id": "anthropic-pro-2", "plan": "Claude Pro", "used_percent": 5.0}]}
    with db.connect() as conn:
        model = next((m for m in ("claude-opus-5-5", "claude-sonnet-5-5")
                      if any(r["provider"] == "claude-pro" for r in execution.routes(conn, m))), None)
        if model is None:
            pytest.skip("no claude-pro offer in this database")
        monkeypatch.setattr(execution, "subscription_accounts", accounts(10.0))
        rs = execution.routes(conn, model)
        assert [r.get("account") for r in rs[:2]] == ["anthropic-pro", "anthropic-pro-2"]
        assert rs[1]["subscription"]["account"] == "anthropic-pro-2"
        monkeypatch.setattr(execution, "subscription_accounts", accounts(100.0))
        rs = execution.routes(conn, model)
        assert rs[0].get("account") == "anthropic-pro-2"
        assert [r.get("account") for r in rs].index("anthropic-pro") > next(i for i, r in enumerate(rs) if r["access"] != "subscription")


def test_bridge_usage_is_split_per_account(monkeypatch, tmp_path):
    from walter_router.plan import subscriptions
    log = tmp_path / "usage.jsonl"
    rows = [{"at": "2026-11-07T10:00:00+00:00", "id": "a", "model": "claude-opus-5-5", "tokens": {"input": 1}},
            {"at": "2026-11-07T10:00:00+00:00", "id": "b", "model": "claude-opus-5-5", "tokens": {"input": 2}, "account": "anthropic-pro-2"}]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(claude_pro, "settings", lambda: {"usage_log": str(log)})
    monkeypatch.setattr(subscriptions.instance, "_expand", lambda v: Path(v))
    one = subscriptions.walter_claude_usage(None, {"id": "anthropic-pro"})
    two = subscriptions.walter_claude_usage(None, {"id": "anthropic-pro-2"})
    assert one["claude-opus-5-5"]["input"] == 1 and two["claude-opus-5-5"]["input"] == 2


def test_usage_reads_only_accounts_the_gateway_declares():
    conf = {"accounts": {"anthropic-pro": "claude-subscription", "anthropic-pro-2": "claude-subscription-2"}}
    assert claude_pro.grant_of(conf, "anthropic-pro-2") == "claude-subscription-2"
    assert claude_pro.grant_of({"grant": "claude-subscription"}, None) == "claude-subscription"
    with pytest.raises(ValueError):
        claude_pro.grant_of(conf, "telegram")


def test_a_deadline_after_headers_marks_the_stream_failed():
    """2026-11-07: an Opus answer cut at the deadline once headers were sent left no error, the stream ended cleanly
    and was logged ok with 2 output tokens; the agent retried the same request in a loop."""
    bridge = transport.NativeBridge({}, "claude-test", "token", 60)
    try:
        bridge.sent_headers = True
        bridge.expire()
        assert bridge.error == "claude_transport_timeout" and bridge.done.is_set()
        closed = transport.NativeBridge({}, "claude-test", "token", 60)
        closed.closed.set()
        closed.expire()
        assert closed.error is None          # the caller closed it: its own choice, not a transport failure
        closed.server.server_close()
    finally:
        bridge.server.server_close()


def test_an_agent_call_without_a_timeout_gets_minutes_not_the_transport_default(monkeypatch):
    import types, sys
    spec_g = importlib.util.spec_from_file_location("walter_gateway_t", paths.ROOT / "llm/gateway.py")
    seen = {}

    async def fake_completion(config, token, **kwargs):
        seen.update(kwargs)
        return "ok"
    fake_grants = types.SimpleNamespace(access=lambda ref: "token")
    monkeypatch.setitem(sys.modules, "walter_secrets", types.SimpleNamespace(grants=fake_grants))
    monkeypatch.setitem(sys.modules, "walter_secrets.grants", fake_grants)
    monkeypatch.setitem(sys.modules, "claude_subscription", types.SimpleNamespace(completion=fake_completion))
    gateway = importlib.util.module_from_spec(spec_g)
    spec_g.loader.exec_module(gateway)
    monkeypatch.setitem(gateway._CONF, "claude_subscription", {"grant": "g"})
    asyncio.run(gateway.provider_completion({"provider": "claude-pro"}, model="claude-test", messages=[]))
    assert seen["timeout"] == 600
    asyncio.run(gateway.provider_completion({"provider": "claude-pro"}, model="claude-test", messages=[], timeout=60))
    assert seen["timeout"] == 60

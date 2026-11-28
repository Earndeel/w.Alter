"""Native channel transport and Engine-only write exposure. Fake APIs, no real sends or secrets."""
import json
import builtins
from types import SimpleNamespace
import httpx
import pytest
import walter_beeper as channel

CFG = {"api_url": "http://127.0.0.1:23374", "grant": "fixture", "checkpoint_scope": "fixture"}


def test_memory_cannot_send_even_if_writable_was_requested():
    seen = []
    api = channel.BeeperClient("memory", writable=True, config=CFG, token="fake",
        transport=httpx.MockTransport(lambda r: seen.append(r)))
    with pytest.raises(PermissionError):
        api.send_text("!fixture:test", "fixture")
    assert not seen
    api.close()


def test_send_timeout_is_ambiguous_and_never_retried():
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("accepted but response lost", request=request)
    api = channel.BeeperClient("engine", writable=True, config=CFG, token="fake",
                               transport=httpx.MockTransport(timeout))
    with pytest.raises(httpx.ReadTimeout):
        api.send_text("!fixture:test", "fixture")
    assert len(calls) == 1
    api.close()


def test_retryable_reads_and_no_credentials_in_errors(monkeypatch):
    seen = []
    monkeypatch.setattr(channel.time, "sleep", lambda *_: None)
    def handler(request):
        seen.append(request)
        return httpx.Response(503 if len(seen) == 1 else 200, json={"items": []})
    api = channel.BeeperClient(config=CFG, token="very-private", transport=httpx.MockTransport(handler))
    assert api.get("/v1/chats") == {"items": []} and len(seen) == 2
    api.close()
    api = channel.BeeperClient(config=CFG, token="very-private", transport=httpx.MockTransport(
        lambda r: httpx.Response(403, text="very-private")))
    with pytest.raises(channel.BeeperAPIError) as err:
        api.get("/v1/chats")
    assert str(err.value) == "Beeper API HTTP 403"
    api.close()


def test_websocket_origin_cannot_redirect_bearer_token():
    api = channel.BeeperClient(config=CFG, token="fake", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"endpoints": {"ws_events": "https://untrusted.test/v1/ws"}})))
    with pytest.raises(ValueError, match="outside"):
        api.websocket()
    api.close()


class MCP:
    def __init__(self): self.tools = {}
    def tool(self, **kwargs):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


@pytest.mark.parametrize("client,local,enforced,writer", [
    ("codex", True, True, False), ("unknown", True, True, False),
    ("dsh", False, True, False), ("dsh", True, False, False),
    ("dsh", True, True, True), ("engine", True, True, True),
])
def test_writer_only_exposed_to_local_engine_with_policy(client, local, enforced, writer, monkeypatch):
    monkeypatch.setattr(channel, "engine_policy_enabled", lambda: enforced)
    mcp = MCP()
    channel.register(mcp, client, local)
    assert "beeper_read" in mcp.tools
    assert ("beeper_send_message" in mcp.tools) is writer


def test_writer_fails_closed_if_policy_is_switched_off(monkeypatch):
    monkeypatch.setattr(channel, "engine_policy_enabled", lambda: True)
    mcp = MCP(); channel.register(mcp, "dsh", True)
    monkeypatch.setattr(channel, "engine_policy_enabled", lambda: False)
    with pytest.raises(PermissionError):
        mcp.tools["beeper_send_message"]("!fixture:test", "fixture")


@pytest.mark.parametrize('allowed',[True,False])
def test_standalone_mcp_uses_the_same_secrets_grant_through_its_cli(monkeypatch,allowed):
    original=builtins.__import__
    def no_secrets(name,*args,**kwargs):
        if name=='walter_secrets':
            raise ModuleNotFoundError("No module named 'walter_secrets'",name='walter_secrets')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',no_secrets)
    def grant(argv,**kwargs):
        assert argv==['walter-secret','grant','access','fixture','--as','engine']
        assert kwargs['capture_output'] and kwargs['timeout']==45
        return SimpleNamespace(returncode=0 if allowed else 1,stdout='fake' if allowed else '',stderr='private')
    monkeypatch.setattr(channel.subprocess,'run',grant)
    if allowed:
        api=channel.BeeperClient('engine',config=CFG)
        assert api.http.headers['Authorization']=='Bearer fake'
        api.close()
    else:
        with pytest.raises(PermissionError,match='grant unavailable'):
            channel.BeeperClient('engine',config=CFG)

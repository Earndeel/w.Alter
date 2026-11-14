"""Model calls and their guards: the Router must route the poste to the required provider, one subscription
account must have room under the pause threshold, a reading is never asked twice, the route header is checked and
an invalid answer is retried once. walter-router and the gateway are simulated."""
import json

import httpx
import pytest

from walter_devboard import llm
from walter_devboard.config import Config

CFG = Config(token_file=None)


def subs(*percents, age=10.0):
    return [{"id": "openai-plus", "meter": {"used_percent": 1.0, "age_s": age}}] + [
        {"id": "anthropic-pro" + ("" if i == 0 else f"-{i + 1}"), "meter": {"used_percent": p, "age_s": age}}
        for i, p in enumerate(percents)]


@pytest.fixture
def router(monkeypatch):
    state = {"pick": {"model_id": "claude-haiku-5-5", "provider": "claude-pro"}, "subs": subs(49.0), "calls": []}

    def fake(*args):
        state["calls"].append(args)
        if args[0] == "pick":
            return state["pick"]
        if args[:2] == ("subscriptions", "show"):
            return state["subs"]
        if args[:2] == ("subscriptions", "refresh"):
            return {}
        raise AssertionError(args)
    monkeypatch.setattr(llm, "_router", fake)
    monkeypatch.setenv("WALTER_LLM_TOKEN", "test-token")
    return state


@pytest.fixture
def gateway(monkeypatch):
    """Queue of (content, route header) answers; every POST body is kept."""
    state = {"answers": [], "posts": []}

    def handler(request: httpx.Request):
        state["posts"].append(json.loads(request.content))
        content, route = state["answers"].pop(0)
        return httpx.Response(200, headers={"X-Walter-Route": route},
                              json={"choices": [{"message": {"content": content}}]})
    monkeypatch.setattr(llm, "_transport", lambda: httpx.MockTransport(handler))
    return state


def ask(conn, key="k1", validate=lambda r: None):
    return llm.read(CFG, conn, key=key, kind="session", source_ref="s1", from_seq=1, to_seq=9,
                    prompt=[{"role": "user", "content": "lis"}], schema={"type": "object"}, validate=validate)


def test_gate_pauses_at_70(router):
    router["subs"] = subs(70.0, 100.0)
    with pytest.raises(llm.Paused) as e:
        llm.gate(CFG)
    assert e.value.reason == "quota"


def test_gate_passes_if_one_account_has_room(router):
    router["subs"] = subs(100.0, 49.0)
    llm.gate(CFG)


def test_gate_pauses_on_wrong_provider(router, gateway, conn):
    router["pick"] = {"model_id": "gpt-x", "provider": "codex"}
    with pytest.raises(llm.Paused) as e:
        ask(conn)
    assert e.value.reason == "route"
    assert gateway["posts"] == []


def test_gate_unknown_quota(router):
    router["subs"] = [{"id": "anthropic-pro", "meter": None}]
    with pytest.raises(llm.Paused) as e:
        llm.gate(CFG)
    assert e.value.reason == "unknown_quota"


def test_gate_refreshes_stale_meter(router):
    router["subs"] = subs(49.0, age=5000.0)
    with pytest.raises(llm.Paused) as e:   # still stale after refresh → unknown
        llm.gate(CFG)
    assert e.value.reason == "unknown_quota"
    assert ("subscriptions", "refresh", "anthropic-pro") in router["calls"]


def test_memo_never_asks_twice(router, gateway, conn):
    gateway["answers"] = [('{"a": 1}', "claude-pro/claude-haiku-5-5")]
    assert ask(conn) == {"a": 1}
    assert ask(conn) == {"a": 1}
    assert len(gateway["posts"]) == 1
    body = gateway["posts"][0]
    assert body["model"] == "exact:claude-haiku-5-5@claude-pro"
    assert body["response_format"]["type"] == "json_schema"


def test_route_header_checked(router, gateway, conn):
    gateway["answers"] = [('{"a": 1}', "kie/x")]
    with pytest.raises(llm.Paused) as e:
        ask(conn)
    assert e.value.reason == "route"
    row = conn.execute("select status from devboard.readings where key = 'k1'").fetchone()
    assert row["status"] == "failed"


def test_invalid_then_valid_retries_once(router, gateway, conn):
    gateway["answers"] = [("pas du json", "claude-pro/m"), ('{"a": 2}', "claude-pro/m")]
    assert ask(conn) == {"a": 2}
    assert len(gateway["posts"]) == 2
    row = conn.execute("select status, attempts from devboard.readings where key = 'k1'").fetchone()
    assert row["status"] == "done" and row["attempts"] == 2


def test_invalid_twice_fails(router, gateway, conn):
    def strict(r):
        if "cards" not in r:
            raise ValueError("cards manquant")
    gateway["answers"] = [("pas du json", "claude-pro/m"), ('{"a": 2}', "claude-pro/m")]
    assert ask(conn, validate=strict) is None
    row = conn.execute("select status, attempts, error from devboard.readings where key = 'k1'").fetchone()
    assert row["status"] == "failed" and row["attempts"] == 2 and "cards" in row["error"]


def test_failed_reading_is_retried_later(router, gateway, conn):
    gateway["answers"] = [("x", "claude-pro/m"), ("y", "claude-pro/m"), ('{"a": 3}', "claude-pro/m")]
    assert ask(conn) is None
    assert ask(conn) == {"a": 3}


def test_key_depends_on_range_and_version():
    k = llm.key("session", "s1", 1, 9)
    assert k != llm.key("session", "s1", 1, 10)
    assert len(k) == 64

"""Model calls and their guards: the Router must route the poste to the required provider, one subscription
account must have room under the pause threshold, a reading is never asked twice, the route header is checked and
an invalid answer is retried once. walter-router and the gateway are simulated."""
import json  # noqa: F401

import httpx
import pytest

from walter_devboard import llm
from conftest import subs
from walter_devboard.config import Config

CFG = Config(token_file=None)


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
    assert "response_format" not in body            # the subscription bridge refuses json_schema (2026-11-14)
    assert '"type": "object"' in body["messages"][0]["content"]


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


def test_retry_tells_the_model_why(router, gateway, conn):
    def strict(r):
        if "cards" not in r:
            raise ValueError("cards manquant")
    gateway["answers"] = [('{"a": 1}', "claude-pro/m"), ('{"cards": []}', "claude-pro/m")]
    assert ask(conn, validate=strict) == {"cards": []}
    assert "cards manquant" in gateway["posts"][1]["messages"][-1]["content"]


def test_schema_checked_locally(router, gateway, conn):
    schema = {"type": "object", "required": ["cards"], "properties": {"cards": {"type": "array"}}}
    gateway["answers"] = [('{"cards": "non"}', "claude-pro/m"), ('{"cards": []}', "claude-pro/m")]
    r = llm.read(CFG, conn, key="k2", kind="session", source_ref="s1", from_seq=1, to_seq=9,
                 prompt=[{"role": "system", "content": "règles"}, {"role": "user", "content": "lis"}],
                 schema=schema, validate=lambda r: None)
    assert r == {"cards": []}
    assert gateway["posts"][0]["messages"][0]["content"].startswith("règles")
    assert "array" in gateway["posts"][1]["messages"][-1]["content"]


# --- final review fixes (C1, I1) ---

@pytest.mark.parametrize("answer", [502, 503, 429, httpx.ConnectError("walter-llm down")])
def test_gateway_failure_is_a_pause_not_an_attempt(router, gateway, conn, answer):
    """All Pro accounts refused (502 'every route failed'), gateway down, or rate limited: stop and keep the slice."""
    gateway["answers"] = [answer]
    with pytest.raises(llm.Paused) as e:
        ask(conn)
    assert e.value.reason in ("quota", "gateway")
    row = conn.execute("select attempts from devboard.readings where key = 'k1'").fetchone()
    assert row is None or row["attempts"] == 0
    assert len(gateway["posts"]) == 1                    # no second call in the same pass


def test_gate_pauses_on_the_five_hour_window(router):
    """The weekly meter has room but the session window (shared with the owner's own Claude use) is at 80 %."""
    router["subs"] = subs(100.0, 57.0)
    router["pick"] = {**router["pick"], "execution": [
        {"provider": "claude-pro", "account": "anthropic-pro-2",
         "subscription": {"account": "anthropic-pro-2", "quota_used_percent": 57.0, "session_used_percent": 80.0}},
        {"provider": "claude-pro", "account": "anthropic-pro",
         "subscription": {"account": "anthropic-pro", "quota_used_percent": 100.0, "session_used_percent": 0.0}}]}
    with pytest.raises(llm.Paused) as e:
        llm.gate(CFG)
    assert e.value.reason == "quota"
    router["pick"]["execution"][0]["subscription"]["session_used_percent"] = 40.0
    assert llm.gate(CFG)["model_id"] == "claude-haiku-5-5"


def test_wrong_route_failure_survives_the_rollback(router, gateway, conn):
    gateway["answers"] = [('{"a": 1}', "kie/x")]
    with pytest.raises(llm.Paused):
        with conn.transaction():
            ask(conn, key="k-route")
    from walter_devboard import db
    with db.autocommit() as other:
        row = other.execute("select status, error from devboard.readings where key = 'k-route'").fetchone()
        other.execute("delete from devboard.readings where key = 'k-route'")
    assert row and row["status"] == "failed" and "kie/x" in row["error"]

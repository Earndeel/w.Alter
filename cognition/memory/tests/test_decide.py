"""llm.decide / llm.rerank through a stubbed walter-llm gateway (SOCLE A6): Memory's door (privacy, pseudonymisation,
ledger) stays here, execution is the gateway's; no provider endpoint, key or model name in Memory. No network."""
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walter_memory import llm  # noqa: E402


class Gateway:
    """Stands in for httpx.post on 127.0.0.1:8894: records each request, answers with a fixed reply."""

    def __init__(self, status=200, body=None, exc=None):
        self.status, self.body, self.exc, self.seen = status, body, exc, []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.seen.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        if self.exc:
            raise self.exc
        return types.SimpleNamespace(status_code=self.status, headers={}, json=lambda: self.body)


@pytest.fixture
def door(monkeypatch):
    rows = []
    monkeypatch.setattr(llm, "_log", lambda **row: rows.append(row))
    monkeypatch.setattr(llm, "_gateway_token", lambda: "memory-token")
    monkeypatch.setattr(llm, "budget_status", lambda b: None)
    return rows


OK = {"answers": {"a": {"choice": "x"}}, "usage": {"cost": 0}, "model": "vendor/decider-20261101",
      "provider": "openrouter", "route": "openrouter/vendor/decider",
      "calls": [{"provider": "openrouter", "model": "vendor/decider", "ok": True, "seconds": 0.4,
                 "cost_usd": 0.00007, "input_tokens": 12}],
      "attempts": []}


def test_decide_posts_to_the_gateway_with_memory_token_and_books_each_call(monkeypatch, door):
    gw = Gateway(body={**OK, "samples": 3, "calls": OK["calls"] * 3})
    monkeypatch.setattr(llm.httpx, "post", gw)
    out = llm.decide({"text": "x"}, {"a": {}}, processor="t", privacy_class="cloud_allowed", samples=3)
    (req,) = gw.seen
    assert req["url"].endswith("/v1/decisions") and req["headers"] == {"Authorization": "Bearer memory-token"}
    assert req["json"]["samples"] == 3 and "models" not in req["json"] and req["json"]["paid_floor_usd"] == 1.0
    assert out["answers"] == {"a": {"choice": "x"}} and out["samples"] == 3 and out["route"] == "openrouter/vendor/decider"
    assert [(r["status"], r["provider"], r["cost_usd"], r["latency_ms"]) for r in door] == [
        ("ok", "openrouter", 0.00007, 400)] * 3


def test_redacted_state_is_pseudonymised_before_the_gateway(monkeypatch, door):
    gw = Gateway(body=OK)
    monkeypatch.setattr(llm.httpx, "post", gw)
    llm.decide({"text": "appelle le +33 6 12 34 56 78"}, {"a": {}}, processor="t", privacy_class="redacted_cloud")
    assert "+33" not in json.dumps(gw.seen[0]["json"])


def test_local_only_is_refused_without_any_request(monkeypatch, door):
    gw = Gateway(body=OK)
    monkeypatch.setattr(llm.httpx, "post", gw)
    with pytest.raises(llm.PrivacyRefused):
        llm.decide({"text": "x"}, {}, processor="t", privacy_class="local_only")
    assert not gw.seen and door[-1]["status"] == "refused_privacy"


def test_named_models_are_a_request_to_the_gateway_never_executed_here(monkeypatch, door):
    gw = Gateway(body=OK)
    monkeypatch.setattr(llm.httpx, "post", gw)
    llm.decide({}, {"a": {}}, processor="t", privacy_class="cloud_allowed", models=("a/b", "c/d"), budget="backfill")
    assert gw.seen[0]["json"]["models"] == ["a/b", "c/d"] and gw.seen[0]["json"]["paid_floor_usd"] == 5.0
    llm.decide({}, {"a": {}}, processor="t", privacy_class="cloud_allowed", model="a/b")
    assert gw.seen[1]["json"]["models"] == ["a/b"]


def test_whole_chain_failure_is_explicit_and_every_attempt_is_booked(monkeypatch, door):
    body = {"error": {"message": "no decision model answered", "task": "decision",
                      "attempts": [{"provider": "openrouter", "model": "a/b", "reason": "HTTP 402"},
                                   {"provider": "cloudflare", "model": "cloudflare/clef", "reason": "missing_grant: X"}],
                      "calls": [{"provider": "openrouter", "model": "a/b", "ok": False, "error": "HTTP 402", "seconds": 0.1},
                                {"provider": "cloudflare", "model": "cloudflare/clef", "ok": False,
                                 "error": "missing_grant: X", "seconds": 0}]}}
    monkeypatch.setattr(llm.httpx, "post", Gateway(status=502, body=body))
    with pytest.raises(RuntimeError, match="no decision model answered.*HTTP 402.*missing_grant"):
        llm.decide({}, {"a": {}}, processor="t", privacy_class="cloud_allowed")
    assert [(r["status"], r["model"]) for r in door] == [("error", "a/b"), ("error", "cloudflare/clef")]


def test_gateway_down_fails_explicitly_with_no_builtin_chain(monkeypatch, door):
    import httpx
    monkeypatch.setattr(llm.httpx, "post", Gateway(exc=httpx.ConnectError("refused")))
    with pytest.raises(RuntimeError, match="walter-llm unreachable"):
        llm.decide({}, {"a": {}}, processor="t", privacy_class="cloud_allowed")
    assert door[-1]["status"] == "error"
    assert not hasattr(llm, "DECIDE_CHAIN") and not hasattr(llm, "decide_chain") and not hasattr(llm, "_decide_once")


def test_rerank_goes_to_the_gateway_and_books_the_route(monkeypatch, door):
    gw = Gateway(body={"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}],
                       "model": "vendor/reranker", "provider": "openrouter", "usage": {"total_tokens": 30},
                       "cost_usd": 0.00001})
    monkeypatch.setattr(llm.httpx, "post", gw)
    out = llm.rerank("q", ["a", "b"], top_n=2, processor="search.rerank", privacy_class="redacted_cloud")
    assert [r["index"] for r in out["results"]] == [1, 0]
    assert gw.seen[0]["url"].endswith("/v1/rerank") and gw.seen[0]["json"]["top_n"] == 2 and "model" not in gw.seen[0]["json"]
    assert door[-1]["model"] == "vendor/reranker" and door[-1]["cost_usd"] == 0.00001 and door[-1]["status"] == "ok"


def test_rerank_failure_is_raised_and_booked(monkeypatch, door):
    monkeypatch.setattr(llm.httpx, "post", Gateway(status=502, body={"error": {"message": "no rerank route answered",
                                                                               "attempts": [{"reason": "HTTP 500"}]}}))
    with pytest.raises(llm.GatewayError, match="HTTP 502"):
        llm.rerank("q", ["a", "b"], processor="search.rerank", privacy_class="cloud_allowed")
    assert door[-1]["status"] == "error"


def test_memory_holds_no_provider_endpoint_key_or_model_name():
    src = Path(llm.__file__).read_text() + (Path(llm.__file__).parent / "search.py").read_text()
    for needle in ("openrouter.ai", "api.cloudflare.com", "OPENROUTER_API_KEY", "CLOUDFLARE_AI_TOKEN",
                   "mercury-decide", "cloudflare/clef", "rerank-4-fast", "rerank-5-fast", "grants.env_value"):
        assert needle not in src, needle

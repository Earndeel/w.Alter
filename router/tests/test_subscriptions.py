from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from walter_router import db, execution, subscriptions

POLICY = {"reserve_percent": 85, "exhausted_percent": 98}
NOW = datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    with db.connect() as c:
        yield c
        c.rollback()


@pytest.mark.parametrize("used,status", [(17, "ok"), (84.9, "ok"), (85, "reserve"), (97, "reserve"), (98, "exhausted")])
def test_classify_thresholds(used, status):
    w = [{"used_percent": used, "resets_at": NOW + timedelta(days=2), "source": "codex_usage_api", "age_s": 30}]
    assert subscriptions.classify(w, POLICY, NOW)["status"] == status


def test_classify_takes_the_fullest_window_and_ignores_a_passed_reset():
    w = [{"used_percent": 99, "resets_at": NOW - timedelta(minutes=1), "source": "codex_usage_api", "age_s": 30},
         {"used_percent": 40, "resets_at": NOW + timedelta(days=3), "source": "codex_usage_api", "age_s": 30}]
    assert subscriptions.classify(w, POLICY, NOW) == {"status": "ok", "used_percent": 40.0}


def test_classify_without_fresh_reading_is_unknown():
    w = [{"used_percent": 99, "resets_at": None, "source": "codex_usage_api", "age_s": 7 * 3600}]
    assert subscriptions.classify(w, POLICY, NOW)["status"] == "unknown"
    assert subscriptions.classify([], POLICY, NOW)["status"] == "unknown"


def test_units_ignore_cache_reads_and_weight_output():
    weights = {"input": 1, "cache_write": 1, "cache_read": 0, "output": 5}
    usage = {"input_tokens": 10, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 10 ** 9,
             "output_tokens": 200}
    assert subscriptions.units(usage, weights) == 10 + 1000 + 1000


def test_claude_estimate_dedupes_calls_and_keeps_plan_models(tmp_path):
    def line(ts, mid, model, out):
        return json.dumps({"type": "assistant", "timestamp": ts, "requestId": f"r{mid}",
                           "message": {"id": mid, "model": model, "usage": {"output_tokens": out}}})
    recent = (NOW - timedelta(days=1)).isoformat()
    old = (NOW - timedelta(days=8)).isoformat()
    (tmp_path / "a.jsonl").write_text("\n".join([line(recent, 1, "claude-opus-5-5", 100),
                                                 line(recent, 1, "claude-opus-5-5", 100),   # same call twice
                                                 line(recent, 2, "claude-fable-5-1", 100),  # not in the plan
                                                 line(old, 3, "claude-opus-5-5", 100)]))     # outside 7 days
    weights = {"input": 1, "cache_write": 1, "cache_read": 0, "output": 5}
    got = subscriptions.claude_units(NOW - timedelta(days=7), weights, ["claude-opus-5-5"], root=tmp_path)
    assert (got["units"], got["calls"]) == (500, 1)


def test_values_give_what_monsieur_pays_per_api_dollar():
    sub = {"price_usd_month": 20, "plan_values": [{"model_id": "m", "usd_month": 200}]}
    assert subscriptions.values(sub)[0]["pays_per_api_dollar"] == 0.1


@pytest.mark.parametrize("status,first", [("ok", "openai-codex"), ("reserve", "kie-codex"),
                                          ("exhausted", "kie-codex")])
def test_routes_follow_the_quota(conn, monkeypatch, status, first):
    monkeypatch.setattr(subscriptions, "route_status",
                        lambda c, p: {"status": status, "used_percent": None, "sub_id": "openai-plus"})
    rs = execution.routes(conn, "gpt-6-1-sol", "medium")
    assert rs and rs[0]["hermes_provider"] == first
    sub = [r for r in rs if r["access"] == "subscription"]
    if status == "exhausted":
        assert rs[-1]["access"] == "subscription"
    elif status == "reserve":  # after the paid routes, but kept
        assert sub and rs.index(sub[0]) > 0

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from walter_router.plan import subscriptions

NOW = datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)
ROW = dict.fromkeys(subscriptions.KINDS, 0)


def test_units_ignore_cache_reads_and_weight_output():
    weights = {"input": 1, "cache_write": 1, "cache_read": 0, "output": 5}
    row = {**ROW, "input": 10, "cache_write": 600, "cache_write_1h": 400, "cache_read": 10 ** 9, "output": 200}
    assert subscriptions.units(row, weights) == 10 + 1000 + 1000


def test_claude_code_usage_dedupes_calls_and_splits_cache_writes(tmp_path):
    def line(ts, mid, model, **usage):
        return json.dumps({"type": "assistant", "timestamp": ts, "requestId": f"r{mid}",
                           "message": {"id": mid, "model": model, "usage": usage}})
    recent, old = (NOW - timedelta(days=1)).isoformat(), (NOW - timedelta(days=8)).isoformat()
    w = {"cache_creation_input_tokens": 100, "cache_creation": {"ephemeral_1h_input_tokens": 70}}
    (tmp_path / "a.jsonl").write_text("\n".join([
        line(recent, 1, "claude-opus-5-5", output_tokens=10, **w),
        line(recent, 1, "claude-opus-5-5", output_tokens=10, **w),   # same call logged twice
        line(old, 2, "claude-opus-5-5", output_tokens=10)]))          # outside the window
    got = subscriptions.claude_code_usage(NOW - timedelta(days=7), root=tmp_path)
    assert got == {"claude-opus-5-5": {**ROW, "output": 10, "cache_write": 30, "cache_write_1h": 70}}


def test_codex_cli_usage_takes_the_last_cumulative_count_and_splits_cached(tmp_path):
    def tc(inp, cached, out):
        return json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
            "input_tokens": inp, "cached_input_tokens": cached, "cache_write_input_tokens": 0, "output_tokens": out}}}})
    (tmp_path / "s.jsonl").write_text("\n".join([json.dumps({"type": "turn_context", "payload": {"model": "gpt-6.1-sol"}}),
                                                 tc(100, 80, 5), tc(300, 250, 9)]))
    got = subscriptions.codex_cli_usage(None, root=tmp_path)
    assert got == {"gpt-6-1-sol": {**ROW, "input": 50, "cache_read": 250, "output": 9}}


def test_priced_values_known_models_and_lists_the_others():
    prices = {"m": {"input": 2, "output": 10, "cache_read": 0.1, "cache_write": 2.5, "cache_write_1h": 4}}
    acc = {"m": {**ROW, "input": 1e6, "output": 1e6, "cache_read": 1e7}, "x": {**ROW, "output": 5}}
    got = subscriptions.priced(acc, prices)
    assert got["api_value_usd"] == 13.0 and got["unpriced_models"] == ["x"] and got["total_tokens"] == 12e6 + 5


def test_blended_price_on_semianalysis_mix_matches_their_opus_figure():
    opus = {"input": 4, "output": 20, "cache_read": 0.2, "cache_write": 5, "cache_write_1h": 8}
    mix = {"cache_read": 0.966, "cache_write": 0.026, "input": 0.004, "output": 0.003}
    assert abs(subscriptions.blended(opus, mix) - 0.399) < 0.001   # OrcaRouter's 0.399 $/M on the same mix


def test_measured_point_value_needs_three_points_in_one_week():
    reset = NOW + timedelta(days=3)

    def r(pct, value, hours, resets=reset):
        return {"used_percent": pct, "resets_at": resets, "read_at": NOW + timedelta(hours=hours),
                "detail": {"cumulative_api_value_usd": value}}
    assert subscriptions.measured_point_value([r(17, 100, 0), r(19, 104, 1)]) is None
    got = subscriptions.measured_point_value([r(17, 100, 0), r(18, 101, 1), r(21, 110, 2),
                                              r(2, 300, 3, resets=reset + timedelta(days=7))])
    assert got["points"] == 4 and got["usd_per_point"] == 2.5 and got["week_usd"] == 250

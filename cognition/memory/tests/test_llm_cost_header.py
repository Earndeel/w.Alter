"""llm.chat books the gateway's cost when the provider reports none (2026-11-07: 142 Venice calls booked at zero)."""
import types

from walter_memory import llm


def _call(monkeypatch, headers, usage):
    logged = []
    monkeypatch.setattr(llm, "_log", lambda **kw: logged.append(kw))
    monkeypatch.setattr(llm, "budget_status", lambda b: None)
    monkeypatch.setattr(llm, "_gateway_token", lambda: "t")
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: types.SimpleNamespace(
        status_code=200, headers={"x-walter-route": "venice/claude-opus-5", **headers},
        json=lambda: {"choices": [{"message": {"content": "ok"}}], "usage": usage}))
    out = llm.chat([{"role": "user", "content": "x"}], poste="document", processor="t", privacy_class="cloud_allowed")
    return out, logged[-1]


def test_gateway_estimate_is_booked_when_the_provider_reports_no_cost(monkeypatch):
    out, row = _call(monkeypatch, {"x-walter-cost-usd": "0.0123", "x-walter-cost-status": "estimated_price"},
                     {"prompt_tokens": 10, "completion_tokens": 2})
    assert out["cost_usd"] == row["cost_usd"] == 0.0123 and row["provider"] == "venice"


def test_reported_cost_wins_and_no_header_stays_unknown(monkeypatch):
    out, row = _call(monkeypatch, {"x-walter-cost-usd": "9"}, {"cost": 0.5})
    assert row["cost_usd"] == 0.5
    out, row = _call(monkeypatch, {}, {})
    assert row["cost_usd"] is None

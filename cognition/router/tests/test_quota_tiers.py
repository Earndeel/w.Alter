"""Owner, 2026-11-16: luxury points never set the L3 ceiling; while a subscription's quota lasts L2/L3 are its best
models, and once every account is spent the declared substitute runs instead of the API price."""
from __future__ import annotations

from walter_router.analysis import select as sel
from walter_router.analysis import tiers
from walter_router.serve import execution, routes


def _p(m, v, s, c, sub=None, paid=None):
    route = {"paid": {"provider": "kie", "cost": paid if paid is not None else c},
             "subscription": sub, "subscription_cost": {"provider": sub, "sub_id": f"{sub}-1", "cost": c} if sub else None}
    return {"model_id": m, "variant": v, "display_name": f"{m} ({v})", "score": s, "score_unit": "AA",
            "cost": c, "real_cost": c, "real_cost_unit": "usd/task", "route": route}


# AA general frontier of 2026-11-16 with ModelDial cost prices (run 820)
POINTS = [_p("claude-sonnet-5-5", "medium", 30.8, 0.0126, "claude-pro", 0.74),
          _p("gpt-6-1-sol", "low", 34.8, 0.0159, "codex", 0.16),
          _p("gpt-6-1-terra", "medium", 38.2, 0.0166, "codex", 0.17),
          _p("gpt-6-1-terra", "high", 42.4, 0.0255, "codex", 0.26),
          _p("gpt-6-1-sol", "medium", 46.3, 0.0353, "codex", 0.36),
          _p("claude-opus-5-5", "medium", 48.2, 0.0416, "claude-pro", 2.45),
          _p("gpt-6-1-sol", "high", 50.3, 0.0580, "codex", 0.59),
          _p("claude-opus-5-5", "high", 51.8, 0.0588, "claude-pro", 3.46),
          _p("gpt-6-1-sol", "xhigh", 52.5, 0.0750, "codex", 0.76),
          _p("gpt-6-1-sol", "max", 54.6, 0.1250, "codex", 1.27),
          _p("gpt-6-astra", "high", 54.8, 0.2265, "codex", 3.24),
          _p("gpt-6-astra", "xhigh", 55.3, 0.2560, "codex", 3.66),
          _p("gpt-6-astra", "max", 56.9, 0.4370, "codex", 6.25),
          _p("claude-opus-5-5", "xhigh", 57.4, 0.1026, "claude-pro", 6.05),
          _p("claude-opus-5-5", "max", 59.1, 0.1703, "claude-pro", 10.04),
          _p("gemini-4-carbon", "high", 60.0, 3.1022),
          _p("claude-fable-5-2", "max", 64.6, 26.5386)]


def _id(p):
    return p and f'{p["model_id"]}/{p["variant"]}'


def test_a_luxury_point_no_longer_sets_the_ceiling():
    t = tiers.compute(POINTS)
    assert _id(t["L3"]) == "claude-opus-5-5/xhigh"          # was Gemini 4 Carbon high at 3.10 $ (band set by Fable)
    assert t["params"]["ceiling"] == 59.1
    assert t["params"]["luxury"] == ["gemini-4-carbon/high", "claude-fable-5-2/max"]
    assert {_id(p) for p in t["frontier"]} >= {"claude-fable-5-2/max"}   # still shown on the frontier


def test_subscription_rule_spreads_l2_and_l3_over_two_subscriptions():
    q = tiers.quota_levels(POINTS, sel._on_subscription, sel._sub_of)
    assert _id(q["L3"]) == "claude-opus-5-5/xhigh"          # the method on the pool: max = +1.7 pts for 66 % more quota
    assert _id(q["L2"]) == "gpt-6-1-sol/xhigh"              # another subscription, cheaper than L3 (Astra, Sol max: dearer)


def test_l2_stays_on_l3_subscription_when_it_is_the_only_one():
    claude = [p for p in POINTS if p["route"]["subscription"] == "claude-pro"]
    q = tiers.quota_levels(claude, sel._on_subscription, sel._sub_of)
    assert (_id(q["L2"]), _id(q["L3"])) == ("claude-opus-5-5/high", "claude-opus-5-5/xhigh")


def test_tier_rows_carry_the_substitute_once_the_quota_is_spent():
    rows = {r["level"]: r for r in sel._tier_rows(POINTS) if r["level"] in ("L1", "L2", "L3")}
    assert (rows["L1"]["model_id"], rows["L1"]["variant"]) == ("gpt-6-1-terra", "medium")
    assert "quota_rule" not in rows["L1"]["reasons"]
    l2, l3 = rows["L2"]["reasons"]["quota_rule"], rows["L3"]["reasons"]["quota_rule"]
    assert (rows["L2"]["model_id"], rows["L2"]["variant"]) == ("gpt-6-1-sol", "xhigh")
    assert (rows["L3"]["model_id"], rows["L3"]["variant"]) == ("claude-opus-5-5", "xhigh")
    assert l3["route_provider"] == "claude-pro" and l2["route_provider"] == "codex"
    assert l3["when_quota_spent"]["pin"] == "gpt-6-1-sol/max"        # Claude spent: above L2, on ChatGPT Plus
    assert l2["when_quota_spent"]["pin"] == "claude-opus-5-5/high"   # ChatGPT spent: Claude, not Sol at API price


def test_a_paid_pick_better_than_every_subscription_keeps_the_method():
    pts = [_p("a", "low", 36, 0.01, "codex"), _p("b", "medium", 40, 0.02, "codex"), _p("c", "", 44, 0.03),
           _p("d", "", 46, 0.05), _p("e", "", 47, 0.08)]
    rows = {r["level"]: r for r in sel._tier_rows(pts) if r["level"] in ("L2", "L3")}
    assert all("quota_rule" not in r["reasons"] for r in rows.values())


def _sub(account, weekly, session=0):
    return {"provider": "claude-pro", "access": "subscription",
            "subscription": {"account": account, "quota_used_percent": weekly, "session_used_percent": session}}


def test_exhausted_means_every_account_spent():
    assert not execution.subscription_exhausted([_sub("a", 100), _sub("b", 75), {"access": "paid"}])
    assert execution.subscription_exhausted([_sub("a", 100), _sub("b", 92), {"access": "paid"}])
    assert execution.subscription_exhausted([_sub("a", 100), _sub("b", 10, session=100)])
    assert not execution.subscription_exhausted([{"access": "paid"}])          # no subscription: nothing to switch


class _Conn:
    def execute(self, *_a, **_k):
        return self

    def fetchone(self):
        return {"interface": "chat", "requirements": {}, "modes": []}


def _with(monkeypatch, opus_routes):
    calls = []

    def fake_routes(conn, model_id, variant="", **_k):
        calls.append(model_id)
        return opus_routes if model_id == "claude-opus-5-5" else [{"provider": "codex", "access": "subscription"}]
    monkeypatch.setattr(execution, "routes", fake_routes)
    monkeypatch.setattr(routes.knowledge, "level_when_quota_spent",
                        lambda task, level: "gpt-6-1-sol/xhigh" if level == "L3" else None)
    out = routes.with_execution(_Conn(), {"task": "general", "level": "L3", "model_id": "claude-opus-5-5",
                                          "variant": "max"})
    return out, calls


def test_spent_subscription_switches_to_the_declared_substitute(monkeypatch):
    out, calls = _with(monkeypatch, [_sub("a", 100), _sub("b", 95), {"provider": "kie", "access": "paid"}])
    assert (out["model_id"], out["variant"]) == ("gpt-6-1-sol", "xhigh") and calls == ["claude-opus-5-5", "gpt-6-1-sol"]
    assert out["quota_switch"]["from"]["model_id"] == "claude-opus-5-5" and out["provider"] == "codex"


def test_quota_left_on_one_account_keeps_the_tier_model(monkeypatch):
    out, calls = _with(monkeypatch, [_sub("a", 100), _sub("b", 40), {"provider": "kie", "access": "paid"}])
    assert out["model_id"] == "claude-opus-5-5" and "quota_switch" not in out and calls == ["claude-opus-5-5"]

from __future__ import annotations

import pytest

from walter_router.analysis import alerts
from walter_router.analysis import telegram
from walter_router.serve import choose
from walter_router.store import db
from walter_router.analysis import tiers


def _p(m, v, s, c):
    return {"model_id": m, "variant": v, "score": s, "cost": c}


# AA frontier of 2026-10-02 (score, real cost per task)
POINTS = [_p("gpt-6-luna", "high", 32.9, 0.009), _p("gpt-6-luna", "xhigh", 34.6, 0.013),
          _p("gpt-6-luna", "max", 38.1, 0.020), _p("mimo-v2-6-flash", "", 37.9, 0.062),
          _p("gpt-6-1-sol", "low", 42.1, 0.039), _p("gpt-6-1-sol", "medium", 47.8, 0.064),
          _p("gpt-6-1-sol", "high", 50.2, 0.096), _p("gpt-6-1-sol", "xhigh", 51.0, 0.118),
          _p("gpt-6-1-sol", "max", 51.8, 0.217), _p("gpt-6-astra", "xhigh", 52.4, 0.646),
          _p("gpt-6-astra", "max", 52.7, 0.912), _p("claude-opus-5-5", "high", 53.6, 0.729),
          _p("claude-opus-5-5", "xhigh", 56.0, 1.384), _p("claude-opus-5-5", "max", 57.6, 2.393)]


def test_method_reproduces_the_owners_tiers():
    t = tiers.compute(POINTS)
    assert (t["L1"]["model_id"], t["L1"]["variant"]) == ("gpt-6-luna", "max")
    assert (t["L2"]["model_id"], t["L2"]["variant"]) == ("gpt-6-1-sol", "medium")
    assert (t["L3"]["model_id"], t["L3"]["variant"]) == ("claude-opus-5-5", "high")


def test_frontier_drops_dominated_points():
    names = {(p["model_id"], p["variant"]) for p in tiers.frontier(POINTS)}
    assert ("mimo-v2-6-flash", "") not in names and ("gpt-6-astra", "max") not in names


def test_a_cheaper_better_model_moves_the_tier():
    t = tiers.compute(POINTS + [_p("newcomer", "", 49.0, 0.05)])
    assert t["L2"]["model_id"] == "newcomer"


@pytest.fixture
def conn():
    with db.connect() as c:
        if choose.latest_run(c) is None:
            pytest.skip("no refresh yet")
        yield c
        c.rollback()


def test_divergence_from_declared_tier_raises_one_alert_and_adopting_pins_it(conn):
    run = choose.latest_run(conn)
    conn.execute("""update models.preferences set pinned_model_id = 'gpt-6-luna', pinned_variant = 'high'
                    where task = 'general' and role = 'L1'""")
    conn.execute("delete from models.alerts where kind = 'tier'")
    assert alerts.tiers(conn, run, {"new": {}, "nerf": {}, "price_drop": {}}) == []  # nothing changed: silent
    conn.execute("delete from models.alerts where kind = 'tier'")
    news = {"new": {}, "nerf": {}, "price_drop": {"gpt-6-luna": [{"provider": "kie", "drop_pct": 30}]}}
    created = alerts.tiers(conn, run, news)
    assert created == ["L1:gpt-6-luna/max"]
    a = conn.execute("select * from models.alerts where kind = 'tier'").fetchone()
    assert "Niveau texte L1" in telegram.render([a], conn)
    alerts.verdict(conn, a["alert_id"], "adopted")
    p = conn.execute("select pinned_variant from models.preferences where task = 'general' and role = 'L1'").fetchone()
    assert p["pinned_variant"] == "max"


def test_specialised_tasks_keep_only_the_best(conn):
    n = conn.execute("""select count(*) as n from models.selection where run_id = %s and task = 'coding'
                        and level = 'best'""", (choose.latest_run(conn),)).fetchone()["n"]
    assert n <= 1


def test_static_orchestrator_comparison_is_never_news(conn):
    """Astra vs Sol on poste criteria is a comparison between known models: never sent (2026-10-04)."""
    conn.execute("""insert into models.alerts (kind, task, role, subject, evidence, status)
                    values ('tier', 'general', 'orchestrator', 'zz-model', '{}', 'open')""")
    assert not [a for a in alerts.pending(conn) if a["role"] == "orchestrator"]

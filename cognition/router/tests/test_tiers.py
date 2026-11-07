from __future__ import annotations

import json

import pytest

from walter_router.analysis import alerts, changes
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
    """The method's L1 is read from the latest run (live data: it moved with the AA index, 2026-10-28)."""
    run = choose.latest_run(conn)
    l1 = conn.execute("""select model_id, variant from models.selection where run_id = %s and task = 'general'
                         and level = 'L1'""", (run,)).fetchone()
    if not l1:
        pytest.skip("no L1 on the latest run")
    conn.execute("""update models.preferences set pinned_model_id = %s, pinned_variant = 'zz-other'
                    where task = 'general' and role = 'L1'""", (l1["model_id"],))
    conn.execute("delete from models.alerts where kind = 'tier'")
    assert alerts.tiers(conn, run, {"new": {}, "nerf": {}, "price_drop": {}}) == []  # nothing changed: silent
    conn.execute("delete from models.alerts where kind = 'tier'")
    news = {"new": {}, "nerf": {}, "price_drop": {l1["model_id"]: [{"provider": "kie", "drop_pct": 30}]}}
    created = alerts.tiers(conn, run, news)
    assert f'L1:{l1["model_id"]}/{l1["variant"]}' in created
    a = conn.execute("select * from models.alerts where kind = 'tier' and role = 'L1'").fetchone()
    assert "Niveau texte L1" in telegram.render([a], conn)
    alerts.verdict(conn, a["alert_id"], "adopted")
    p = conn.execute("select pinned_variant from models.preferences where task = 'general' and role = 'L1'").fetchone()
    assert p["pinned_variant"] == l1["variant"]


def test_specialised_tasks_keep_only_the_best(conn):
    n = conn.execute("""select count(*) as n from models.selection where run_id = %s and task = 'coding'
                        and level = 'best'""", (choose.latest_run(conn),)).fetchone()["n"]
    assert n <= 1


def test_static_orchestrator_comparison_is_never_news(conn):
    """Astra vs Sol on poste criteria is a comparison between known models: never sent (2026-10-04)."""
    conn.execute("""insert into models.alerts (kind, task, role, subject, evidence, status)
                    values ('tier', 'general', 'orchestrator', 'zz-model', '{}', 'open')""")
    assert not [a for a in alerts.pending(conn) if a["role"] == "orchestrator"]


def _snapshot(conn, raw: dict, hours_ago: int, kind: str = "aa") -> int:
    return conn.execute("""insert into models.snapshots (kind, fetched_at, source_url, sha256, row_count, raw)
                           values (%s, now() - make_interval(hours => %s), 'test', md5(random()::text), 0, %s::jsonb)
                           returning snapshot_id""", (kind, hours_ago, json.dumps(raw))).fetchone()["snapshot_id"]


def test_a_new_index_version_is_a_rebase_not_a_nerf(conn):
    """AA Intelligence Index v4 → v5.0 (2026-10-28): the board is not compared across versions."""
    board = "aa_intelligence:intelligence"
    v4 = _snapshot(conn, {"data": []}, 72)
    first_v5 = _snapshot(conn, {"index_version": "5.0", "data": []}, 48)      # before `versions` existed
    v5 = _snapshot(conn, {"index_version": "5.0", "versions": {board: "5.0"}, "data": []}, 0)
    unread = _snapshot(conn, {"index_version": None, "versions": {}, "data": []}, 0)
    assert changes.rebased_boards(conn, first_v5, v4) == {board: {"before": None, "after": "5.0"}}
    assert changes.rebased_boards(conn, v5, first_v5) == {}
    assert changes.rebased_boards(conn, unread, v5) == {}          # methodology page down: not a change


def test_domain_indexes_and_updated_evaluations_rebase_per_board(conn):
    from walter_router.research.benchmarks import aa_evaluations
    labels = aa_evaluations.versions({"omniscience": {"type": "updated", "description": "AA-Omniscience v1.1"},
                                      "aa-3d": {"type": "new"}}, "5.0")
    assert labels["aa_eval:idx_economics"] == "intelligence 5.0" and labels["aa_eval:omniscience"] == "AA-Omniscience v1.1"
    assert "aa_eval:aa_3d" not in labels and "aa_eval:gpqa" not in labels
    before = _snapshot(conn, {"data": []}, 72, kind="aa_eval")
    after = _snapshot(conn, {"versions": labels, "data": []}, 0, kind="aa_eval")
    assert set(changes.rebased_boards(conn, after, before)) == set(labels)


def test_a_rebase_puts_each_diverging_tier_to_the_owner(conn):
    run = choose.latest_run(conn)
    conn.execute("""update models.preferences set pinned_model_id = 'gpt-6-luna', pinned_variant = 'zz-none'
                    where task = 'general' and role in ('L1', 'L2', 'L3')""")
    conn.execute("delete from models.alerts where kind = 'tier'")
    rebased = {"new": {}, "nerf": {}, "price_drop": {},
               "rebased": {"aa_intelligence:intelligence": {"before": None, "after": "5.0"}}}
    created = alerts.tiers(conn, run, rebased)
    assert created and all(c.split(":")[0] in ("L1", "L2", "L3") for c in created)
    why = conn.execute("select evidence from models.alerts where kind = 'tier' limit 1").fetchone()["evidence"]["why"]
    assert why == ["nouvel AA Intelligence Index (version précédente → v5.0) : niveaux recalculés"]

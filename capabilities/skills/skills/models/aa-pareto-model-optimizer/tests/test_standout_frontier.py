from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "refresh.py"
SPEC = importlib.util.spec_from_file_location("aa_refresh_standout", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _row(name: str, score: float, cost: float) -> dict[str, object]:
    return {
        "name": name,
        "intelligence_index": score,
        "aa_cost_per_task_intelligence_usd": cost,
    }


def test_standout_frontier_keeps_knee_and_endpoints() -> None:
    frontier = [
        _row("cheap", 10.0, 1.0),
        _row("weak-step", 11.0, 2.0),
        _row("knee", 18.0, 4.0),
        _row("best", 20.0, 8.0),
    ]

    standout = MODULE.standout_frontier(
        frontier,
        score_field="intelligence_index",
        cost_field="aa_cost_per_task_intelligence_usd",
    )

    assert [row["name"] for row in standout] == ["cheap", "knee", "best"]


def test_standout_frontier_removes_collinear_log_cost_step() -> None:
    frontier = [
        _row("cheap", 10.0, 1.0),
        _row("middle", 13.0, 2.0),
        _row("best", 16.0, 4.0),
    ]

    standout = MODULE.standout_frontier(
        frontier,
        score_field="intelligence_index",
        cost_field="aa_cost_per_task_intelligence_usd",
    )

    assert [row["name"] for row in standout] == ["cheap", "best"]


def test_compact_frontier_rows_explains_neighbor_tradeoffs() -> None:
    rows = [
        _row("cheap", 10.0, 1.0),
        _row("knee", 15.0, 2.0),
        _row("best", 17.0, 8.0),
    ]

    public = MODULE.compact_frontier_rows(
        rows,
        score_field="intelligence_index",
        cost_field="aa_cost_per_task_intelligence_usd",
    )

    knee = public[1]
    assert knee["previous_model"] == "cheap"
    assert knee["score_gain_vs_previous"] == 5.0
    assert knee["cost_multiple_vs_previous"] == 2.0
    assert knee["next_model"] == "best"
    assert knee["score_gain_to_next"] == 2.0
    assert knee["cost_multiple_to_next"] == 4.0
    assert knee["knee_strength"] > 1.0


def test_make_frontier_explains_standouts_against_strict_neighbors():
    rows = [
        _row("cheap", 10.0, 1.0),
        _row("weak", 11.0, 2.0),
        _row("knee", 18.0, 4.0),
        _row("best", 20.0, 8.0),
    ]

    result = MODULE.make_frontier(
        rows,
        "intelligence_index",
        "aa_cost_per_task_intelligence_usd",
        0.0,
        0.5,
        0.5,
        10.0,
        2.0,
    )

    selected = result["standout_frontier"]
    assert [item["model"] for item in selected] == ["cheap", "knee", "best"]
    assert selected[1]["previous_model"] == "weak"
    assert selected[1]["knee_strength"] >= 2.0
    assert selected[1]["selection_reason"] == "local_knee_vs_strict_frontier_neighbors"


def test_value_anchor_uses_strongest_global_supported_knee():
    supported = [
        _row("cheap", 80.0, 1.0),
        _row("value-anchor", 100.0, 2.0),
        _row("premium", 120.0, 100.0),
    ]

    anchor = MODULE.select_value_anchor(
        supported,
        "intelligence_index",
        "aa_cost_per_task_intelligence_usd",
    )

    assert anchor["name"] == "value-anchor"


def test_upgrade_ladder_keeps_only_decreasing_marginal_returns():
    strict = [
        _row("value-anchor", 100.0, 1.0),
        _row("local-artifact", 102.0, 4.0),
        _row("budget-upgrade", 114.0, 5.0),
        _row("bad-middle-tier", 115.0, 7.0),
        _row("quality-upgrade", 118.0, 7.5),
        _row("quality-ceiling", 119.0, 9.0),
    ]

    result = MODULE.build_upgrade_ladder(
        strict,
        strict[0],
        "intelligence_index",
        "aa_cost_per_task_intelligence_usd",
    )

    assert [item["model"] for item in result["tiers"]] == [
        "value-anchor",
        "budget-upgrade",
        "quality-upgrade",
        "quality-ceiling",
    ]
    assert [item["model"] for item in result["removed_by_marginal_return"]] == [
        "local-artifact",
        "bad-middle-tier",
    ]
    marginal_returns = [
        item["marginal_score_per_dollar_from_previous"]
        for item in result["tiers"][1:]
    ]
    assert marginal_returns == [3.5, 1.6, 2 / 3]
    assert result["tiers"][2]["incremental_cost_per_score_point"] == 0.625
    assert result["tiers"][-1]["tier_type"] == "quality_ceiling"

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "refresh.py"
SPEC = importlib.util.spec_from_file_location("aa_refresh", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _row(name: str, score: float, cost: float) -> dict[str, object]:
    return {
        "name": name,
        "score": score,
        "task_cost_usd": cost,
    }


def test_epsilon_prune_removes_small_premium_quality_steps() -> None:
    frontier = [
        _row("cheap", 10.0, 1.00),
        _row("middle", 11.0, 1.05),
        _row("near_best", 12.0, 1.09),
        _row("expensive", 13.0, 1.30),
    ]

    retained, removed = MODULE.epsilon_prune(
        frontier,
        score_field="score",
        cost_field="task_cost_usd",
        min_score_gain=0.5,
        max_cost_premium_pct=10.0,
    )

    assert [row["name"] for row in retained] == ["near_best", "expensive"]
    assert [row["name"] for row in removed] == ["cheap", "middle"]


def test_epsilon_prune_keeps_a_large_cost_step() -> None:
    frontier = [
        _row("cheap", 10.0, 1.00),
        _row("better_but_expensive", 11.0, 1.11),
    ]

    retained, removed = MODULE.epsilon_prune(
        frontier,
        score_field="score",
        cost_field="task_cost_usd",
        min_score_gain=0.5,
        max_cost_premium_pct=10.0,
    )

    assert [row["name"] for row in retained] == ["cheap", "better_but_expensive"]
    assert removed == []


def test_pragmatic_frontier_applies_marginal_cost_cap_and_preserves_ceiling() -> None:
    rows = [
        {
            "name": "MiMo-V2.6-Pro",
            "slug": "mimo-v2-6-pro",
            "intelligence_index": 46.3242065310383,
            "aa_cost_per_task_intelligence_usd": 0.13322318937213493,
        },
        {
            "name": "GPT-6 Sol (max)",
            "slug": "gpt-6-sol",
            "intelligence_index": 47.5276426437724,
            "aa_cost_per_task_intelligence_usd": 1.0564240894076389,
        },
        {
            "name": "Efficient step after rejected model",
            "slug": "efficient-step-after-rejected-model",
            "intelligence_index": 47.9,
            "aa_cost_per_task_intelligence_usd": 1.2,
        },
        {
            "name": "Claude Opus 5.5 (medium)",
            "slug": "claude-opus-5-5-medium",
            "intelligence_index": 51.2434931792768,
            "aa_cost_per_task_intelligence_usd": 1.3360093438976588,
        },
        {
            "name": "Claude Opus 5.5 (high)",
            "slug": "claude-opus-5-5-high",
            "intelligence_index": 53.5831959822067,
            "aa_cost_per_task_intelligence_usd": 1.822504718771704,
        },
        {
            "name": "Claude Opus 5.5 (xhigh)",
            "slug": "claude-opus-5-5-xhigh",
            "intelligence_index": 55.9873505840139,
            "aa_cost_per_task_intelligence_usd": 3.459110175822289,
        },
        {
            "name": "Claude Opus 5.5 (max)",
            "slug": "claude-opus-5-5",
            "intelligence_index": 57.6223698102963,
            "aa_cost_per_task_intelligence_usd": 5.982012019521066,
        },
    ]

    result = MODULE.make_frontier(
        rows,
        "intelligence_index",
        "aa_cost_per_task_intelligence_usd",
        35.0,
        0.5,
        0.5,
        10.0,
        2.0,
        max_incremental_cost_per_score_point=0.75,
    )

    assert [row["model"] for row in result["pragmatic_frontier"]] == [
        "MiMo-V2.6-Pro",
        "Efficient step after rejected model",
        "Claude Opus 5.5 (medium)",
        "Claude Opus 5.5 (high)",
        "Claude Opus 5.5 (xhigh)",
    ]
    removed = result["removed_by_cost_inefficiency"]
    assert [row["model"] for row in removed] == [
        "GPT-6 Sol (max)",
        "Claude Opus 5.5 (max)",
    ]
    assert removed[0]["previous_model"] == "MiMo-V2.6-Pro"
    assert removed[0]["incremental_cost_per_score_point"] == pytest.approx(0.7671374411)
    assert result["upgrade_ladder"]["quality_ceiling"]["model"] == "Claude Opus 5.5 (max)"

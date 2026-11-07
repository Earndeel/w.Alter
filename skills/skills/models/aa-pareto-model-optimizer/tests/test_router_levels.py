from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "router.py"
SPEC = importlib.util.spec_from_file_location("aa_router_levels", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _tier(slug: str, tier_type: str, marginal: float | None, score: float = 50.0, cost: float = 1.0) -> dict:
    return {
        "model": slug, "slug": slug, "tier_type": tier_type, "score": score, "cost_per_task_usd": cost,
        "marginal_score_per_dollar_from_previous": marginal,
    }


def test_knee_is_last_tier_before_sharpest_marginal_fall() -> None:
    # Ladder observed on 2026-10-02: 21.05, 10.85 | 2.4, 1.59, 1.47, 0.65 -> sharpest fall after tier 2.
    tiers = [
        _tier("anchor", "value_anchor", None),
        _tier("sol-high", "marginal_upgrade", 21.05),
        _tier("sol-xhigh", "marginal_upgrade", 10.85),
        _tier("sol-max", "marginal_upgrade", 2.4),
        _tier("opus-high", "marginal_upgrade", 1.59),
        _tier("opus-xhigh", "marginal_upgrade", 1.47),
        _tier("opus-max", "quality_ceiling", 0.65),
    ]
    assert MODULE.ladder_knee(tiers)["slug"] == "sol-xhigh"


def test_knee_without_two_segments_falls_back() -> None:
    anchor = _tier("anchor", "value_anchor", None)
    assert MODULE.ladder_knee([anchor])["slug"] == "anchor"
    assert MODULE.ladder_knee([anchor, _tier("ceiling", "quality_ceiling", 3.0)])["slug"] == "ceiling"


def test_levels_use_knee_for_l2() -> None:
    tiers = [
        _tier("anchor", "value_anchor", None, 46.0, 0.13),
        _tier("a", "marginal_upgrade", 20.0, 50.0, 0.32),
        _tier("b", "marginal_upgrade", 2.0, 51.0, 0.82),
        _tier("ceiling", "quality_ceiling", 1.5, 52.0, 1.5),
    ]
    aa = {"frontiers": {"intelligence_aa": {"upgrade_ladder": {"tiers": tiers, "quality_ceiling": tiers[-1]}}}}
    levels = MODULE.build_intelligence_levels(aa)
    assert [lvl["slug"] for lvl in levels] == ["anchor", "a", "ceiling"]


def test_no_knee_when_marginal_return_barely_falls() -> None:
    # 2026-10-02 image-to-video ladder: 6250 then 5550 Elo per $ (x1.13) -> keep climbing to the top tier.
    tiers = [
        _tier("seedance", "value_anchor", None),
        _tier("pixverse", "marginal_upgrade", 6250.0),
        _tier("minimax-h3", "quality_ceiling", 5550.0),
    ]
    assert MODULE.ladder_knee(tiers)["slug"] == "minimax-h3"

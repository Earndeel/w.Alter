"""Pareto mathematics of the text tiers: the cost/score frontier with epsilon and pragmatic pruning
(make_frontier) and the knee of the upgrade ladder (ladder_knee). Taken over unchanged from the
aa-pareto-model-optimizer skill (refresh.py, router.py) on 2026-10-21, so the router no longer loads code from a
Hermes skill folder."""
from __future__ import annotations

import math
from typing import Any

def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None

def compact_frontier_row(row: dict[str, Any], score_field: str, cost_field: str) -> dict[str, Any]:
    score = finite_number(row.get(score_field))
    cost = finite_number(row.get(cost_field))
    kie_task_fields = {
        "aa_cost_per_task_intelligence_usd": "kie_reference_cost_per_task_intelligence_usd",
    }
    if cost_field.startswith("kie_reference_cost_per_task_"):
        kie_cost = cost
        aa_cost_field = cost_field.replace(
            "kie_reference_cost_per_task_", "aa_cost_per_task_", 1
        )
        aa_cost = finite_number(row.get(aa_cost_field))
    else:
        kie_cost = finite_number(row.get(kie_task_fields.get(cost_field, "")))
        aa_cost = cost
    kie_reduction = None
    if aa_cost is not None and aa_cost > 0 and kie_cost is not None:
        kie_reduction = (1 - kie_cost / aa_cost) * 100
    return {
        "model": row.get("name"),
        "slug": row.get("slug"),
        "score": score,
        "cost_per_task_usd": cost,
        "score_per_dollar": score / cost if score is not None and cost else None,
        "kie_cost_per_task_usd": kie_cost,
        "kie_cost_reduction_vs_aa_pct": kie_reduction,
        "kie_source_url": row.get("kie_source_url"),
        "kie_nominal_discount_pct": row.get("kie_nominal_discount_vs_published_official_pct"),
        "kie_claimed_discount_pct": row.get("kie_claimed_discount_pct"),
        "kie_input_price_1m_usd": row.get("kie_input_price_1m_usd"),
        "kie_output_price_1m_usd": row.get("kie_output_price_1m_usd"),
        "kie_vs_aa_reference_blended_delta_pct": row.get("kie_vs_aa_reference_blended_delta_pct"),
        "kie_pricing_consistency": row.get("kie_pricing_consistency"),
        "kie_pricing_status": row.get("kie_pricing_status"),
    }

def _log_cost_slope(
    left: dict[str, Any],
    right: dict[str, Any],
    score_field: str,
    cost_field: str,
) -> float:
    left_score = finite_number(left.get(score_field)) or 0.0
    right_score = finite_number(right.get(score_field)) or 0.0
    left_cost = finite_number(left.get(cost_field)) or 0.0
    right_cost = finite_number(right.get(cost_field)) or 0.0
    delta_log_cost = math.log(right_cost) - math.log(left_cost)
    if delta_log_cost <= 0:
        return float("inf")
    return (right_score - left_score) / delta_log_cost

def supported_frontier(
    frontier: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
) -> list[dict[str, Any]]:
    """Keep supported Pareto points on score versus logarithmic cost.

    Strict Pareto points can still be economically redundant. The upper
    concave envelope keeps only points that are optimal for some trade-off
    between score and proportional cost. Interior marginal slopes must
    decrease as cost rises; collinear or below-envelope points are removed.
    """
    hull: list[dict[str, Any]] = []
    for row in frontier:
        cost = finite_number(row.get(cost_field))
        score = finite_number(row.get(score_field))
        if cost is None or cost <= 0 or score is None:
            continue
        if hull:
            previous_cost = finite_number(hull[-1].get(cost_field)) or 0.0
            if math.isclose(cost, previous_cost, rel_tol=1e-12, abs_tol=0.0):
                previous_score = finite_number(hull[-1].get(score_field)) or 0.0
                if score > previous_score:
                    hull[-1] = row
                continue
        while len(hull) >= 2:
            incoming = _log_cost_slope(hull[-2], hull[-1], score_field, cost_field)
            outgoing = _log_cost_slope(hull[-1], row, score_field, cost_field)
            if incoming > outgoing + 1e-12:
                break
            hull.pop()
        hull.append(row)
    return hull

def standout_frontier(
    frontier: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
    minimum_knee_strength: float = 2.0,
) -> list[dict[str, Any]]:
    """Keep endpoints and local knees relative to strict-frontier neighbors."""
    if len(frontier) <= 2:
        return list(frontier)
    selected = [frontier[0]]
    for index in range(1, len(frontier) - 1):
        incoming = _log_cost_slope(
            frontier[index - 1], frontier[index], score_field, cost_field
        )
        outgoing = _log_cost_slope(
            frontier[index], frontier[index + 1], score_field, cost_field
        )
        if outgoing > 0 and incoming / outgoing >= minimum_knee_strength:
            selected.append(frontier[index])
    selected.append(frontier[-1])
    return selected

def select_value_anchor(
    supported: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
) -> dict[str, Any]:
    """Select the strongest global knee on the supported Pareto frontier."""
    eligible = [
        row
        for row in supported
        if finite_number(row.get(score_field)) is not None
        and (finite_number(row.get(cost_field)) or 0) > 0
    ]
    if not eligible:
        raise ValueError("Cannot select a value anchor from an empty frontier")
    if len(eligible) < 3:
        return max(
            eligible,
            key=lambda row: (finite_number(row.get(score_field)) or 0)
            / (finite_number(row.get(cost_field)) or float("inf")),
        )

    knees: list[tuple[float, dict[str, Any]]] = []
    for index in range(1, len(eligible) - 1):
        incoming = _log_cost_slope(
            eligible[index - 1], eligible[index], score_field, cost_field
        )
        outgoing = _log_cost_slope(
            eligible[index], eligible[index + 1], score_field, cost_field
        )
        if outgoing > 0:
            knees.append((incoming / outgoing, eligible[index]))
    if knees:
        return max(knees, key=lambda item: item[0])[1]
    return max(
        eligible,
        key=lambda row: (finite_number(row.get(score_field)) or 0)
        / (finite_number(row.get(cost_field)) or float("inf")),
    )

def build_upgrade_ladder(
    strict: list[dict[str, Any]],
    value_anchor: dict[str, Any],
    score_field: str,
    cost_field: str,
    display_cost_field: str | None = None,
) -> dict[str, Any]:
    """Build the raw-cost concave envelope above a global value anchor."""
    rendered_cost_field = display_cost_field or cost_field
    anchor_score = finite_number(value_anchor.get(score_field))
    anchor_cost = finite_number(value_anchor.get(cost_field))
    if anchor_score is None or anchor_score <= 0 or anchor_cost is None or anchor_cost <= 0:
        raise ValueError("Value anchor must have positive score and cost")

    ordered = sorted(
        strict,
        key=lambda row: (
            finite_number(row.get(cost_field)) or float("inf"),
            -(finite_number(row.get(score_field)) or 0),
        ),
    )
    candidates = [value_anchor] + [
        row
        for row in ordered
        if row is not value_anchor
        and (finite_number(row.get(cost_field)) or 0) > anchor_cost
        and (finite_number(row.get(score_field)) or 0) > anchor_score
    ]

    def marginal_return(left: dict[str, Any], right: dict[str, Any]) -> float:
        left_score = finite_number(left.get(score_field)) or 0
        right_score = finite_number(right.get(score_field)) or 0
        left_cost = finite_number(left.get(cost_field)) or 0
        right_cost = finite_number(right.get(cost_field)) or 0
        cost_delta = right_cost - left_cost
        return (right_score - left_score) / cost_delta if cost_delta > 0 else float("inf")

    selected: list[dict[str, Any]] = []
    removed_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        while len(selected) >= 2:
            previous = selected[-2]
            middle = selected[-1]
            incoming = marginal_return(previous, middle)
            outgoing = marginal_return(middle, candidate)
            if incoming > outgoing + 1e-12:
                break
            removed_rows.append(selected.pop())
        selected.append(candidate)

    removed: list[dict[str, Any]] = []
    for middle in sorted(
        removed_rows,
        key=lambda row: finite_number(row.get(cost_field)) or float("inf"),
    ):
        middle_cost = finite_number(middle.get(cost_field)) or 0
        cheaper = [
            row
            for row in selected
            if (finite_number(row.get(cost_field)) or 0) < middle_cost
        ]
        dearer = [
            row
            for row in selected
            if (finite_number(row.get(cost_field)) or 0) > middle_cost
        ]
        if not cheaper or not dearer:
            continue
        previous = cheaper[-1]
        next_row = dearer[0]
        rendered = compact_frontier_row(middle, score_field, rendered_cost_field)
        rendered.update(
            {
                "previous_model": previous.get("name"),
                "next_model": next_row.get("name"),
                "incoming_marginal_score_per_dollar": marginal_return(
                    previous, middle
                ),
                "outgoing_marginal_score_per_dollar": marginal_return(
                    middle, next_row
                ),
                "bypass_marginal_score_per_dollar": marginal_return(
                    previous, next_row
                ),
                "removal_reason": (
                    "marginal return rises after this point; the next retained "
                    "model offers a more efficient incremental upgrade"
                ),
            }
        )
        removed.append(rendered)

    tiers: list[dict[str, Any]] = []
    previous_marginal: float | None = None
    for index, row in enumerate(selected):
        score = finite_number(row.get(score_field)) or 0
        cost = finite_number(row.get(cost_field)) or 0
        previous = selected[index - 1] if index else None
        previous_score = finite_number(previous.get(score_field)) if previous else None
        previous_cost = finite_number(previous.get(cost_field)) if previous else None
        cost_multiple = cost / anchor_cost
        uplift_pct = (score / anchor_score - 1) * 100
        marginal = marginal_return(previous, row) if previous else None
        rendered = compact_frontier_row(row, score_field, rendered_cost_field)
        rendered.update(
            {
                "tier_type": (
                    "value_anchor"
                    if index == 0
                    else "quality_ceiling"
                    if index + 1 == len(selected)
                    else "marginal_upgrade"
                ),
                "actual_uplift_pct_from_anchor": uplift_pct,
                "score_gain_from_anchor": score - anchor_score,
                "cost_multiple_from_anchor": cost_multiple,
                "performance_uplift_pct_per_cost_doubling_from_anchor": (
                    uplift_pct / math.log2(cost_multiple)
                    if cost_multiple > 1
                    else None
                ),
                "previous_tier": previous.get("name") if previous else None,
                "score_gain_from_previous_tier": (
                    score - previous_score if previous_score is not None else None
                ),
                "cost_increase_from_previous_tier_usd": (
                    cost - previous_cost if previous_cost is not None else None
                ),
                "cost_multiple_from_previous_tier": (
                    cost / previous_cost
                    if previous_cost is not None and previous_cost > 0
                    else None
                ),
                "marginal_score_per_dollar_from_previous": marginal,
                "incremental_cost_per_score_point": (
                    1 / marginal if marginal is not None and marginal > 0 else None
                ),
                "marginal_return_retained_vs_previous_segment_pct": (
                    marginal / previous_marginal * 100
                    if marginal is not None
                    and previous_marginal is not None
                    and previous_marginal > 0
                    else None
                ),
            }
        )
        tiers.append(rendered)
        if marginal is not None:
            previous_marginal = marginal

    return {
        "method": (
            "strongest knee on the global supported frontier, then upper concave "
            "envelope of score versus raw incremental task cost"
        ),
        "decision_rule": (
            "retain tiers only while marginal score gained per additional dollar "
            "decreases monotonically"
        ),
        "tiers": tiers,
        "quality_ceiling": tiers[-1] if tiers else None,
        "removed_by_marginal_return": removed,
    }

def compact_frontier_rows(
    rows: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        previous = rows[index - 1] if index else None
        next_row = rows[index + 1] if index + 1 < len(rows) else None
        score = finite_number(row.get(score_field)) or 0.0
        cost = finite_number(row.get(cost_field)) or 0.0
        result = compact_frontier_row(row, score_field, cost_field)

        previous_score = finite_number(previous.get(score_field)) if previous else None
        previous_cost = finite_number(previous.get(cost_field)) if previous else None
        next_score = finite_number(next_row.get(score_field)) if next_row else None
        next_cost = finite_number(next_row.get(cost_field)) if next_row else None

        result.update(
            {
                "previous_model": previous.get("name") if previous else None,
                "score_gain_vs_previous": (
                    score - previous_score if previous_score is not None else None
                ),
                "score_gain_vs_previous_pct": (
                    (score / previous_score - 1) * 100
                    if previous_score is not None and previous_score != 0
                    else None
                ),
                "cost_increase_vs_previous_usd": (
                    cost - previous_cost if previous_cost is not None else None
                ),
                "cost_multiple_vs_previous": (
                    cost / previous_cost
                    if previous_cost is not None and previous_cost > 0
                    else None
                ),
                "next_model": next_row.get("name") if next_row else None,
                "score_gain_to_next": next_score - score if next_score is not None else None,
                "score_gain_to_next_pct": (
                    (next_score / score - 1) * 100
                    if next_score is not None and score != 0
                    else None
                ),
                "cost_increase_to_next_usd": (
                    next_cost - cost if next_cost is not None else None
                ),
                "cost_multiple_to_next": (
                    next_cost / cost if next_cost is not None and cost > 0 else None
                ),
            }
        )
        incoming = (
            _log_cost_slope(previous, row, score_field, cost_field)
            if previous is not None
            else None
        )
        outgoing = (
            _log_cost_slope(row, next_row, score_field, cost_field)
            if next_row is not None
            else None
        )
        result["marginal_score_per_log_cost_from_previous"] = incoming
        result["marginal_score_per_log_cost_to_next"] = outgoing
        result["knee_strength"] = (
            incoming / outgoing
            if incoming is not None and outgoing is not None and outgoing > 0
            else None
        )
        public.append(result)
    return public

def epsilon_prune(
    frontier: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
    min_score_gain: float,
    max_cost_premium_pct: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Remove a cheaper frontier row when a near-priced, better row exists.

    A row is epsilon-dominated when another row improves the benchmark score by
    at least ``min_score_gain`` while costing no more than the configured
    percentage above the row being considered.  This is intentionally applied
    after strict Pareto calculation so the raw mathematical frontier remains
    available for inspection.
    """
    retained: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    cost_multiplier = 1 + max_cost_premium_pct / 100
    for row in frontier:
        score = finite_number(row.get(score_field))
        cost = finite_number(row.get(cost_field))
        dominated = (
            score is not None
            and cost is not None
            and any(
                (finite_number(other.get(score_field)) or 0) - score >= min_score_gain
                and (finite_number(other.get(cost_field)) or float("inf"))
                <= cost * cost_multiplier
                for other in frontier
                if other is not row
            )
        )
        (removed if dominated else retained).append(row)
    return retained, removed

def pragmatic_prune(
    rows: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
    min_gain: float,
    max_incremental_cost_per_score_point: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Filter low-gain and high-marginal-cost steps against retained neighbors.

    Each candidate is compared with the last retained row. Either rejection
    rebases the next candidate on the previous retained option, avoiding gaps
    in the comparison chain.
    """
    retained: list[dict[str, Any]] = []
    removed_by_min_gain: list[dict[str, Any]] = []
    removed_by_cost_inefficiency: list[dict[str, Any]] = []
    for row in rows:
        if not retained:
            retained.append(row)
            continue

        previous = retained[-1]
        previous_score = finite_number(previous.get(score_field))
        score = finite_number(row.get(score_field))
        previous_cost = finite_number(previous.get(cost_field))
        cost = finite_number(row.get(cost_field))
        score_gain = score - previous_score if score is not None and previous_score is not None else None
        cost_increase = cost - previous_cost if cost is not None and previous_cost is not None else None
        incremental_cost = (
            cost_increase / score_gain
            if score_gain is not None and score_gain > 0 and cost_increase is not None
            else None
        )

        if score_gain is None or score_gain < min_gain:
            removed_by_min_gain.append(row)
            continue

        if incremental_cost is not None and incremental_cost <= max_incremental_cost_per_score_point:
            retained.append(row)
            continue

        removed_by_cost_inefficiency.append(
            {
                "row": row,
                "previous_model": previous.get("name") or previous.get("model") or previous.get("slug"),
                "score_gain_from_previous": score_gain,
                "cost_increase_from_previous_usd": cost_increase,
                "incremental_cost_per_score_point": incremental_cost,
                "max_incremental_cost_per_score_point": max_incremental_cost_per_score_point,
                "removal_reason": "incremental cost per score point exceeds the configured cap",
            }
        )
    return retained, removed_by_min_gain, removed_by_cost_inefficiency

def make_frontier(
    rows: list[dict[str, Any]],
    score_field: str,
    cost_field: str,
    minimum_score: float,
    min_gain: float,
    epsilon_score_gain: float,
    epsilon_cost_premium_pct: float,
    minimum_knee_strength: float,
    max_incremental_cost_per_score_point: float = 0.75,
) -> dict[str, Any]:
    eligible = [
        row
        for row in rows
        if finite_number(row.get(score_field)) is not None
        and (finite_number(row.get(cost_field)) or 0) > 0
        and finite_number(row.get(score_field)) > minimum_score
    ]
    strict: list[dict[str, Any]] = []
    for row in eligible:
        score = finite_number(row.get(score_field)) or 0
        cost = finite_number(row.get(cost_field)) or 0
        dominated = any(
            (finite_number(other.get(score_field)) or 0) >= score
            and (finite_number(other.get(cost_field)) or 0) <= cost
            and (
                (finite_number(other.get(score_field)) or 0) > score
                or (finite_number(other.get(cost_field)) or 0) < cost
            )
            for other in eligible
            if other is not row
        )
        if not dominated:
            strict.append(row)
    strict.sort(
        key=lambda row: (
            finite_number(row.get(cost_field)) or 0,
            -(finite_number(row.get(score_field)) or 0),
        )
    )
    supported = supported_frontier(strict, score_field, cost_field)
    if supported:
        value_anchor = select_value_anchor(supported, score_field, cost_field)
        upgrade_ladder = build_upgrade_ladder(
            strict,
            value_anchor,
            score_field,
            cost_field,
        )
    else:
        upgrade_ladder = {
            "method": (
                "strongest knee on the global supported frontier, then upper concave "
                "envelope of score versus raw incremental task cost"
            ),
            "decision_rule": (
                "retain tiers only while marginal score gained per additional dollar "
                "decreases monotonically"
            ),
            "tiers": [],
            "quality_ceiling": None,
            "removed_by_marginal_return": [],
        }
    standout = standout_frontier(
        strict, score_field, cost_field, minimum_knee_strength
    )
    epsilon, removed_by_epsilon = epsilon_prune(
        strict,
        score_field,
        cost_field,
        epsilon_score_gain,
        epsilon_cost_premium_pct,
    )
    pragmatic, removed_by_min_gain, removed_by_cost_inefficiency = pragmatic_prune(
        epsilon,
        score_field,
        cost_field,
        min_gain,
        max_incremental_cost_per_score_point,
    )

    def render_cost_removal(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            **compact_frontier_row(entry["row"], score_field, cost_field),
            **{key: value for key, value in entry.items() if key != "row"},
        }

    strict_public = compact_frontier_rows(strict, score_field, cost_field)
    standout_ids = {id(row) for row in standout}
    strict_public_by_id: dict[int, dict[str, Any]] = {}
    for row, rendered in zip(strict, strict_public):
        rendered["is_standout"] = id(row) in standout_ids
        strict_public_by_id[id(row)] = rendered

    standout_public = [dict(strict_public_by_id[id(row)]) for row in standout]
    for index, rendered in enumerate(standout_public):
        if len(standout_public) == 1:
            reason = "cheapest_and_highest_score_pareto_point"
        elif index == 0:
            reason = "cheapest_pareto_point"
        elif index + 1 == len(standout_public):
            reason = "highest_score_pareto_point"
        else:
            reason = "local_knee_vs_strict_frontier_neighbors"
        rendered["selection_reason"] = reason

    return {
        "score_field": score_field,
        "cost_field": cost_field,
        "minimum_score_exclusive": minimum_score,
        "minimum_gain": min_gain,
        "epsilon_score_gain": epsilon_score_gain,
        "epsilon_cost_premium_pct": epsilon_cost_premium_pct,
        "max_incremental_cost_per_score_point": max_incremental_cost_per_score_point,
        "strict_count": len(strict),
        "supported_count": len(supported),
        "standout_count": len(standout),
        "epsilon_count": len(epsilon),
        "pragmatic_count": len(pragmatic),
        "cost_inefficiency_count": len(removed_by_cost_inefficiency),
        "supported_method": "upper concave envelope of score versus natural-log cost",
        "standout_method": (
            "strict-frontier endpoints plus local knees where incoming/outgoing "
            f"marginal score-per-log-cost ratio is >= {minimum_knee_strength}"
        ),
        "upgrade_ladder": upgrade_ladder,
        "strict_frontier": strict_public,
        "supported_frontier": compact_frontier_rows(
            supported, score_field, cost_field
        ),
        "standout_frontier": standout_public,
        "epsilon_frontier": [
            compact_frontier_row(row, score_field, cost_field) for row in epsilon
        ],
        "pragmatic_frontier": [
            compact_frontier_row(row, score_field, cost_field) for row in pragmatic
        ],
        "removed_by_epsilon": [
            compact_frontier_row(row, score_field, cost_field)
            for row in removed_by_epsilon
        ],
        "removed_by_min_gain": [
            compact_frontier_row(row, score_field, cost_field)
            for row in removed_by_min_gain
        ],
        "removed_by_cost_inefficiency": [
            render_cost_removal(entry) for entry in removed_by_cost_inefficiency
        ],
    }


def ladder_knee(tiers: list[dict[str, Any]], min_drop: float = 2.0) -> dict[str, Any]:
    """Return the upgrade-ladder tier just before the sharpest fall in marginal return.

    Each tier after the anchor carries ``marginal_score_per_dollar_from_previous``. The knee is the
    tier ``i`` maximising ``m[i] / m[i+1]``: buying past it costs disproportionately more per point.
    The fall must be at least ``min_drop``x (same 2.0 default as the standout knee strength);
    otherwise returns stay roughly constant all the way up and the top tier is the sweet spot.
    With fewer than two upgrade segments there is no knee; fall back to the first upgrade or anchor.
    """
    ups = [t for t in tiers[1:] if (t.get("marginal_score_per_dollar_from_previous") or 0) > 0]
    if len(ups) < 2:
        return ups[0] if ups else tiers[0]
    m = [t["marginal_score_per_dollar_from_previous"] for t in ups]
    i = max(range(len(m) - 1), key=lambda k: m[k] / m[k + 1])
    return ups[i] if m[i] / m[i + 1] >= min_drop else ups[-1]

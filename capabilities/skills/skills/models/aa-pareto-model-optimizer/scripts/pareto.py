#!/usr/bin/env python3
"""Compute strict and pragmatic Intelligence/Cost Pareto frontiers."""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from refresh import (
    _log_cost_slope,
    build_upgrade_ladder,
    pragmatic_prune,
    select_value_anchor,
    standout_frontier,
    supported_frontier,
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def eligible_rows(
    rows: list[dict[str, Any]],
    intel_field: str,
    cost_field: str,
    min_intel: float | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    eligible: list[dict[str, Any]] = []
    excluded = {
        "invalid_intelligence": 0,
        "missing_or_nonpositive_cost": 0,
        "at_or_below_min_intel": 0,
        "non_ok_status": 0,
    }

    for source in rows:
        row = dict(source)
        intel = _number(row.get(intel_field))
        cost = _number(row.get(cost_field))
        status = row.get("status")
        if status not in (None, "ok"):
            excluded["non_ok_status"] += 1
            continue
        if intel is None:
            excluded["invalid_intelligence"] += 1
            continue
        if cost is None or cost <= 0:
            excluded["missing_or_nonpositive_cost"] += 1
            continue
        if min_intel is not None and intel <= min_intel:
            excluded["at_or_below_min_intel"] += 1
            continue
        row["_intel"] = intel
        row["_cost"] = cost
        eligible.append(row)
    return eligible, excluded


def strict_frontier(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frontier = []
    for model in rows:
        dominated = any(
            other["_intel"] >= model["_intel"]
            and other["_cost"] <= model["_cost"]
            and (
                other["_intel"] > model["_intel"]
                or other["_cost"] < model["_cost"]
            )
            for other in rows
            if other is not model
        )
        if not dominated:
            frontier.append(model)
    return sorted(frontier, key=lambda row: (row["_cost"], -row["_intel"]))


def pragmatic_frontier(
    frontier: list[dict[str, Any]],
    min_gain: float,
    max_incremental_cost_per_score_point: float = 0.75,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    return pragmatic_prune(
        frontier,
        "_intel",
        "_cost",
        min_gain,
        max_incremental_cost_per_score_point,
    )


def epsilon_prune(
    frontier: list[dict[str, Any]],
    min_score_gain: float,
    max_cost_premium_pct: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Remove a cheaper row when a near-priced, better row exists."""
    retained: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    cost_multiplier = 1 + max_cost_premium_pct / 100
    for row in frontier:
        dominated = any(
            other["_intel"] - row["_intel"] >= min_score_gain
            and other["_cost"] <= row["_cost"] * cost_multiplier
            for other in frontier
            if other is not row
        )
        (removed if dominated else retained).append(row)
    return retained, removed


def public_row(
    row: dict[str, Any],
    previous: dict[str, Any] | None,
    next_row: dict[str, Any] | None,
    intel_field: str,
    cost_field: str,
) -> dict[str, Any]:
    result = {key: value for key, value in row.items() if not key.startswith("_")}
    result[intel_field] = row["_intel"]
    result[cost_field] = row["_cost"]
    result["intel_per_dollar"] = row["_intel"] / row["_cost"]
    result["intel_gain_vs_previous"] = (
        None if previous is None else row["_intel"] - previous["_intel"]
    )
    result["cost_increase_vs_previous_usd"] = (
        None if previous is None else row["_cost"] - previous["_cost"]
    )
    result["cost_multiple_vs_previous"] = (
        None if previous is None else row["_cost"] / previous["_cost"]
    )
    result["next_model"] = None if next_row is None else next_row.get("name")
    result["intel_gain_to_next"] = (
        None if next_row is None else next_row["_intel"] - row["_intel"]
    )
    result["cost_multiple_to_next"] = (
        None if next_row is None else next_row["_cost"] / row["_cost"]
    )
    incoming = (
        _log_cost_slope(previous, row, "_intel", "_cost")
        if previous is not None
        else None
    )
    outgoing = (
        _log_cost_slope(row, next_row, "_intel", "_cost")
        if next_row is not None
        else None
    )
    result["knee_strength"] = (
        incoming / outgoing
        if incoming is not None and outgoing is not None and outgoing > 0
        else None
    )
    return result


def public_frontier(
    rows: list[dict[str, Any]], intel_field: str, cost_field: str
) -> list[dict[str, Any]]:
    return [
        public_row(
            row,
            rows[index - 1] if index else None,
            rows[index + 1] if index + 1 < len(rows) else None,
            intel_field,
            cost_field,
        )
        for index, row in enumerate(rows)
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON array or object containing data[]")
    parser.add_argument("--output", type=Path, help="Write result as JSON")
    parser.add_argument("--csv", type=Path, help="Write standout frontier as CSV")
    parser.add_argument("--intel-field", default="intel")
    parser.add_argument("--cost-field", default="total_cost_usd")
    parser.add_argument(
        "--min-intel",
        type=float,
        help="Exclusive cutoff: models must have intelligence > this value",
    )
    parser.add_argument("--min-gain", type=float, default=0.5)
    parser.add_argument("--min-knee-strength", type=float, default=2.0)
    parser.add_argument(
        "--epsilon-score-gain",
        type=float,
        default=0.5,
        help="Minimum score improvement for epsilon-dominance",
    )
    parser.add_argument(
        "--epsilon-cost-premium-pct",
        type=float,
        default=10.0,
        help="Maximum extra cost percentage allowed for epsilon-dominance",
    )
    parser.add_argument(
        "--max-incremental-cost-per-score-point",
        type=float,
        default=0.75,
        help="Maximum marginal benchmark-task cost in USD per additional Index point",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.min_gain < 0 or args.epsilon_score_gain < 0:
        raise SystemExit("score thresholds must be >= 0")
    if args.min_knee_strength < 1:
        raise SystemExit("--min-knee-strength must be >= 1")

    if args.epsilon_cost_premium_pct < 0:
        raise SystemExit("--epsilon-cost-premium-pct must be >= 0")
    if args.max_incremental_cost_per_score_point < 0:
        raise SystemExit("--max-incremental-cost-per-score-point must be >= 0")

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise SystemExit("Input must be a JSON array of objects or an object with data[]")

    eligible, excluded = eligible_rows(
        rows, args.intel_field, args.cost_field, args.min_intel
    )
    strict = strict_frontier(eligible)
    supported = supported_frontier(strict, "_intel", "_cost")
    if supported:
        value_anchor = select_value_anchor(supported, "_intel", "_cost")
        upgrade_ladder = build_upgrade_ladder(
            strict,
            value_anchor,
            "_intel",
            "_cost",
            display_cost_field=args.cost_field,
        )
    else:
        upgrade_ladder = {
            "decision_rule": (
                "retain tiers only while marginal score gained per additional dollar "
                "decreases monotonically"
            ),
            "tiers": [],
            "quality_ceiling": None,
            "removed_by_marginal_return": [],
        }
    standout = standout_frontier(
        strict, "_intel", "_cost", args.min_knee_strength
    )
    epsilon, removed_by_epsilon = epsilon_prune(
        strict, args.epsilon_score_gain, args.epsilon_cost_premium_pct
    )
    pragmatic, removed_by_min_gain, removed_by_cost_inefficiency = pragmatic_frontier(
        epsilon, args.min_gain, args.max_incremental_cost_per_score_point
    )

    strict_public = public_frontier(strict, args.intel_field, args.cost_field)
    supported_public = public_frontier(supported, args.intel_field, args.cost_field)
    strict_public_by_id = {
        id(row): rendered for row, rendered in zip(strict, strict_public)
    }
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
    pragmatic_public = public_frontier(pragmatic, args.intel_field, args.cost_field)
    epsilon_public = public_frontier(epsilon, args.intel_field, args.cost_field)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metric": args.cost_field,
        "intel_field": args.intel_field,
        "min_intel_exclusive": args.min_intel,
        "min_gain": args.min_gain,
        "min_knee_strength": args.min_knee_strength,
        "epsilon_score_gain": args.epsilon_score_gain,
        "epsilon_cost_premium_pct": args.epsilon_cost_premium_pct,
        "max_incremental_cost_per_score_point": args.max_incremental_cost_per_score_point,
        "counts": {
            "input": len(rows),
            "eligible": len(eligible),
            "strict_frontier": len(strict),
            "supported_frontier": len(supported),
            "standout_frontier": len(standout),
            "epsilon_frontier": len(epsilon),
            "pragmatic_frontier": len(pragmatic),
            "removed_by_cost_inefficiency": len(removed_by_cost_inefficiency),
        },
        "excluded": excluded,
        "upgrade_ladder": upgrade_ladder,
        "strict_frontier": strict_public,
        "supported_frontier": supported_public,
        "standout_frontier": standout_public,
        "epsilon_frontier": epsilon_public,
        "pragmatic_frontier": pragmatic_public,
        "removed_by_epsilon": [
            public_row(row, None, None, args.intel_field, args.cost_field)
            for row in removed_by_epsilon
        ],
        "removed_by_min_gain": [
            public_row(row, None, None, args.intel_field, args.cost_field)
            for row in removed_by_min_gain
        ],
        "removed_by_cost_inefficiency": [
            {
                **public_row(entry["row"], None, None, args.intel_field, args.cost_field),
                **{key: value for key, value in entry.items() if key != "row"},
            }
            for entry in removed_by_cost_inefficiency
        ],
    }

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        fields = list(standout_public[0]) if standout_public else []
        with args.csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            if fields:
                writer.writeheader()
                writer.writerows(standout_public)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

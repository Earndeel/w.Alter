#!/usr/bin/env python3
"""Estimate subscription-equivalent token budgets and routed task costs.

The script keeps subscription economics separate from the official AA frontier.
It converts a fee or an explicit quota into weighted credits, then attaches
within-quota, full-economic, and quota-saturated scenarios to exact AA model
routes.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
TOKEN_KEYS = ("input", "cache_read", "cache_write", "output", "reasoning", "answer")
AA_REFERENCE_FIELDS = (
    "name",
    "slug",
    "intelligence_index",
    "aa_cost_per_task_intelligence_usd",
    "aa_price_input_1m_usd",
    "aa_price_output_1m_usd",
    "aa_price_blended_3_to_1_usd",
)


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def nonnegative_number(value: Any, field: str) -> float | None:
    number = finite_number(value)
    if number is not None and number < 0:
        raise ValueError(f"{field} must be >= 0")
    return number


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def compute_credit_budget(profile: dict[str, Any]) -> dict[str, Any]:
    """Return fee-equivalent credits and the quota used for capacity estimates."""
    fee = nonnegative_number(profile.get("monthly_fee_usd"), "monthly_fee_usd")
    alpha = nonnegative_number(profile.get("fee_allocation_alpha", 1.0), "fee_allocation_alpha")
    credit_value = nonnegative_number(profile.get("credit_value_usd"), "credit_value_usd")
    allocated_fee = fee * alpha if fee is not None and alpha is not None else None
    allocated_budget = (
        allocated_fee / credit_value
        if allocated_fee is not None and credit_value is not None and credit_value > 0
        else None
    )

    quota = _mapping(profile.get("quota"))
    quota_amount = nonnegative_number(quota.get("amount"), "quota.amount")
    quota_unit = quota.get("unit")
    quota_credits = (
        quota_amount
        if quota_amount is not None and quota_unit in {"credit", "credits"}
        else None
    )
    quota_tokens = (
        {str(quota_unit): quota_amount}
        if quota_amount is not None and isinstance(quota_unit, str) and quota_unit.endswith("_tokens")
        else {}
    )

    # A verified explicit credit quota is the capacity constraint. If it is not
    # available, use the fee-equivalent budget as a provisional capacity.
    capacity_credits = quota_credits if quota_credits is not None else allocated_budget
    capacity_basis = "explicit_quota" if quota_credits is not None else "fee_equivalent_budget"
    if capacity_credits is None:
        capacity_basis = "unavailable"

    return {
        "monthly_fee_usd": fee,
        "fee_allocation_alpha": alpha,
        "allocated_fee_usd": allocated_fee,
        "credit_value_usd": credit_value,
        "allocated_budget_credits": allocated_budget,
        "configured_quota_amount": quota_amount,
        "configured_quota_unit": quota_unit,
        "configured_quota_credits": quota_credits,
        "configured_quota_tokens": quota_tokens,
        "capacity_credits": capacity_credits,
        "capacity_basis": capacity_basis,
        "quota_status": quota.get("status", "not_confirmed"),
        "quota_window": quota.get("window"),
    }


def compute_token_equivalents(
    model: dict[str, Any], budget_credits: float | None
) -> dict[str, Any]:
    """Convert a credit budget into separate token equivalents per billing unit."""
    rates = _mapping(model.get("credits_per_million"))
    result: dict[str, Any] = {
        "budget_credits": budget_credits,
        "credits_per_million": {},
    }
    if budget_credits is None:
        for key in rates:
            result[f"{key}_tokens"] = None
        return result

    for key, raw_rate in rates.items():
        rate = nonnegative_number(raw_rate, f"credits_per_million.{key}")
        if rate is None or rate <= 0:
            result["credits_per_million"][key] = rate
            result[f"{key}_tokens"] = None
            continue
        result["credits_per_million"][key] = rate
        result[f"{key}_tokens"] = budget_credits / rate * 1_000_000
    return result


def _task_token_value(task: dict[str, Any], key: str) -> float | None:
    nested = _mapping(task.get("tokens"))
    value = task.get(f"{key}_tokens", nested.get(key))
    return nonnegative_number(value, f"{key}_tokens")


def credits_for_task(model: dict[str, Any], task: dict[str, Any]) -> float | None:
    """Calculate weighted credits for a task with mutually exclusive token fields."""
    rates = _mapping(model.get("credits_per_million"))
    total = 0.0
    observed_component = False
    for key, raw_rate in rates.items():
        rate = nonnegative_number(raw_rate, f"credits_per_million.{key}")
        tokens = _task_token_value(task, str(key))
        if tokens is None:
            continue
        observed_component = True
        if rate is None or rate <= 0:
            raise ValueError(f"credits_per_million.{key} must be > 0 when {key}_tokens is used")
        total += tokens / 1_000_000 * rate
    return total if observed_component else None


def task_capacity(budget_credits: float | None, credits_task: float | None) -> float | None:
    if budget_credits is None or credits_task is None or budget_credits < 0 or credits_task <= 0:
        return None
    return budget_credits / credits_task


def _normalise_task_profiles(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = profile.get("task_profiles") or {}
    if isinstance(raw, list):
        return {
            str(item.get("id")): dict(item)
            for item in raw
            if isinstance(item, dict) and item.get("id")
        }
    if isinstance(raw, dict):
        return {
            str(key): dict(value)
            for key, value in raw.items()
            if isinstance(value, dict)
        }
    return {}


def _public_aa_reference(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row.get(key) for key in AA_REFERENCE_FIELDS if key in row}


def _task_result(
    model: dict[str, Any],
    task: dict[str, Any],
    capacity_credits: float | None,
    allocated_budget_credits: float | None,
) -> dict[str, Any]:
    credits = credits_for_task(model, task)
    return {
        "status": task.get("status", "estimated"),
        "input_tokens": task.get("input_tokens"),
        "cache_read_tokens": task.get("cache_read_tokens"),
        "cache_write_tokens": task.get("cache_write_tokens"),
        "output_tokens": task.get("output_tokens"),
        "reasoning_tokens": task.get("reasoning_tokens"),
        "credits_per_task": credits,
        "capacity_tasks_at_quota": task_capacity(capacity_credits, credits),
        "capacity_tasks_at_budget": task_capacity(allocated_budget_credits, credits),
        "capacity_credits": capacity_credits,
        "allocated_budget_credits": allocated_budget_credits,
    }


def _scenarios(
    profile: dict[str, Any],
    budget: dict[str, Any],
    task_result: dict[str, Any] | None,
    model: dict[str, Any],
) -> dict[str, Any]:
    capacity_tasks = task_result.get("capacity_tasks_at_quota") if task_result else None
    allocated_fee = budget.get("allocated_fee_usd")
    full_cost = (
        allocated_fee / capacity_tasks
        if allocated_fee is not None and capacity_tasks is not None and capacity_tasks > 0
        else None
    )
    fallback = model.get(
        "fallback_cost_per_task_usd",
        profile.get("fallback_cost_per_task_usd"),
    )
    fallback = nonnegative_number(fallback, "fallback_cost_per_task_usd")
    profile_status = profile.get("status", "provisional")
    return {
        "within_quota": {
            "marginal_cost_per_task_usd": 0.0,
            "capacity_tasks": capacity_tasks,
            "capacity_status": profile_status,
            "task_profile": task_result.get("id") if task_result else None,
        },
        "full_economic": {
            "allocated_cost_per_task_usd": full_cost,
            "allocated_fee_usd": allocated_fee,
            "capacity_tasks": capacity_tasks,
            "task_profile": task_result.get("id") if task_result else None,
        },
        "quota_saturated": {
            "cost_per_task_usd": fallback,
            "fallback_route": model.get("fallback_route", profile.get("fallback_route")),
            "task_profile": task_result.get("id") if task_result else None,
        },
    }


def build_snapshot(
    latest: dict[str, Any],
    config: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a subscription-adjusted snapshot from one AA snapshot and config."""
    aa_rows = latest.get("data") if isinstance(latest, dict) else latest
    if not isinstance(aa_rows, list):
        raise ValueError("AA snapshot must contain data[]")
    aa_by_slug = {
        str(row.get("slug")): row
        for row in aa_rows
        if isinstance(row, dict) and row.get("slug")
    }

    profiles = config.get("profiles") if isinstance(config, dict) else None
    if not isinstance(profiles, list):
        raise ValueError("Subscription config must contain profiles[]")

    routes: list[dict[str, Any]] = []
    profile_summaries: list[dict[str, Any]] = []
    for profile in profiles:
        if not isinstance(profile, dict) or not profile.get("id"):
            raise ValueError("Each subscription profile needs an id")
        budget = compute_credit_budget(profile)
        model_configs = profile.get("models") or []
        if not isinstance(model_configs, list):
            raise ValueError(f"Profile {profile['id']} models must be a list")
        task_profiles = _normalise_task_profiles(profile)
        profile_summaries.append(
            {
                "id": profile["id"],
                "provider": profile.get("provider"),
                "status": profile.get("status", "provisional"),
                "monthly_fee_usd": budget["monthly_fee_usd"],
                "fee_allocation_alpha": budget["fee_allocation_alpha"],
                "allocated_budget_credits": budget["allocated_budget_credits"],
                "capacity_credits": budget["capacity_credits"],
                "capacity_basis": budget["capacity_basis"],
                "quota_unit": budget["configured_quota_unit"],
                "quota_window": budget["quota_window"],
            }
        )

        for model in model_configs:
            if not isinstance(model, dict):
                continue
            aa_slug = model.get("aa_slug") or model.get("slug")
            if not aa_slug:
                raise ValueError(f"Profile {profile['id']} contains a model without aa_slug")
            aa_row = aa_by_slug.get(str(aa_slug))
            route_id = f"{profile['id']}::{aa_slug}"
            task_results: dict[str, dict[str, Any]] = {}
            for task_id, task in task_profiles.items():
                result = _task_result(
                    model,
                    task,
                    budget["capacity_credits"],
                    budget["allocated_budget_credits"],
                )
                result["id"] = task_id
                task_results[task_id] = result
            default_task_id = profile.get("default_task_profile")
            if default_task_id is None and len(task_results) == 1:
                default_task_id = next(iter(task_results))
            primary_task = task_results.get(str(default_task_id)) if default_task_id else None
            routes.append(
                {
                    "id": route_id,
                    "subscription_profile": profile["id"],
                    "provider": profile.get("provider"),
                    "status": profile.get("status", "provisional"),
                    "model_identity_status": model.get("model_identity_status", "provisional"),
                    "aa_reference": _public_aa_reference(aa_row),
                    "aa_match_status": "matched" if aa_row is not None else "not_found",
                    "configured_model": {
                        key: value
                        for key, value in model.items()
                        if key not in {"fallback_cost_per_task_usd", "fallback_route"}
                    },
                    "budget": budget,
                    "equivalent_tokens": compute_token_equivalents(
                        model, budget["capacity_credits"]
                    ),
                    "task_profiles": task_results,
                    "default_task_profile": default_task_id,
                    "scenarios": _scenarios(profile, budget, primary_task, model),
                }
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "configured" if routes else "not_configured",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "aa_snapshot_generated_at": latest.get("generated_at") if isinstance(latest, dict) else None,
        "method": {
            "credit_budget": "allocated subscription fee divided by USD value per credit",
            "mixed_task_cost": "sum(tokens_k / 1e6 * credits_per_million_k)",
            "scenarios": ["within_quota", "full_economic", "quota_saturated"],
            "token_equivalent_warning": "input/output/cache equivalents are separate; one raw-token number is not universal",
        },
        "profiles": profile_summaries,
        "routes": routes,
        "counts": {
            "profiles": len(profile_summaries),
            "routes": len(routes),
            "aa_matched_routes": sum(route["aa_match_status"] == "matched" for route in routes),
            "task_profiles": sum(len(route["task_profiles"]) for route in routes),
        },
    }


def _default_cache_dir() -> Path:
    hermes_home = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
    return hermes_home / "cache" / "aa-pareto"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    cache_dir = _default_cache_dir()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=cache_dir / "latest.json")
    parser.add_argument("--config", type=Path, default=cache_dir / "subscriptions.json")
    parser.add_argument("--output", type=Path, default=cache_dir / "subscription-adjusted.json")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.is_file():
        raise SystemExit(f"AA snapshot not found: {args.input}")
    latest = json.loads(args.input.read_text(encoding="utf-8"))
    if not args.config.is_file():
        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": "not_configured",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "aa_snapshot_generated_at": latest.get("generated_at"),
            "profiles": [],
            "routes": [],
            "counts": {"profiles": 0, "routes": 0, "aa_matched_routes": 0, "task_profiles": 0},
            "note": "Create subscriptions.json to enable subscription-adjusted estimates.",
        }
    else:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        payload = build_snapshot(latest, config)
    payload["config_path"] = str(args.config)
    payload["input_path"] = str(args.input)
    _write_json(args.output, payload)
    if not args.quiet:
        counts = payload["counts"]
        print(
            "Subscription snapshot written: "
            f"{counts['profiles']} profiles / {counts['routes']} routes / "
            f"{counts['aa_matched_routes']} AA matched; output={args.output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

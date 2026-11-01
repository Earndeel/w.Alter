from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "subscription.py"
SPEC = importlib.util.spec_from_file_location("aa_subscription", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_credit_budget_and_token_equivalents() -> None:
    profile = {
        "monthly_fee_usd": 20.0,
        "fee_allocation_alpha": 1.0,
        "credit_value_usd": 0.04,
    }
    model = {
        "name": "GPT-5.6 Luna",
        "credits_per_million": {"input": 25.0, "output": 150.0},
    }

    budget = MODULE.compute_credit_budget(profile)
    equivalent = MODULE.compute_token_equivalents(model, budget["allocated_budget_credits"])

    assert budget["allocated_fee_usd"] == 20.0
    assert budget["allocated_budget_credits"] == 500.0
    assert equivalent["input_tokens"] == 20_000_000.0
    assert equivalent["output_tokens"] == 500 * 1_000_000 / 150


def test_mixed_task_credits_and_capacity() -> None:
    model = {
        "credits_per_million": {"input": 25.0, "output": 150.0},
    }
    task = {"input_tokens": 100_000, "output_tokens": 20_000}

    credits = MODULE.credits_for_task(model, task)
    assert credits == 5.5
    assert MODULE.task_capacity(500.0, credits) == 500.0 / 5.5


def test_snapshot_keeps_aa_costs_and_exposes_three_scenarios() -> None:
    latest = {
        "generated_at": "2026-09-01T00:00:00+00:00",
        "data": [
            {
                "name": "GPT-5.6 Luna (max)",
                "slug": "gpt-5-6-luna",
                "intelligence_index": 52.3,
                "aa_cost_per_task_intelligence_usd": 0.048,
            }
        ],
    }
    config = {
        "profiles": [
            {
                "id": "chatgpt_plus_codex",
                "status": "provisional",
                "monthly_fee_usd": 20.0,
                "fee_allocation_alpha": 1.0,
                "credit_value_usd": 0.04,
                "models": [
                    {
                        "aa_slug": "gpt-5-6-luna",
                        "credits_per_million": {"input": 25.0, "output": 150.0},
                    }
                ],
                "task_profiles": {
                    "codex_reference": {
                        "input_tokens": 100_000,
                        "output_tokens": 20_000,
                        "status": "provisional",
                    }
                },
                "fallback_cost_per_task_usd": 0.31,
            }
        ]
    }

    snapshot = MODULE.build_snapshot(latest, config, generated_at="2026-09-01T01:00:00+00:00")
    route = snapshot["routes"][0]

    assert route["aa_reference"]["aa_cost_per_task_intelligence_usd"] == 0.048
    assert route["equivalent_tokens"]["input_tokens"] == 20_000_000.0
    assert route["task_profiles"]["codex_reference"]["credits_per_task"] == 5.5
    assert route["task_profiles"]["codex_reference"]["capacity_tasks_at_budget"] == 500 / 5.5
    assert route["scenarios"]["within_quota"]["marginal_cost_per_task_usd"] == 0.0
    assert route["scenarios"]["full_economic"]["allocated_cost_per_task_usd"] == 20 / (500 / 5.5)
    assert route["scenarios"]["quota_saturated"]["cost_per_task_usd"] == 0.31


def test_snapshot_does_not_invent_task_capacity_without_profile() -> None:
    latest = {"data": []}
    config = {
        "profiles": [
            {
                "id": "unconfigured",
                "monthly_fee_usd": 20.0,
                "credit_value_usd": 0.04,
                "models": [
                    {
                        "aa_slug": "model-a",
                        "credits_per_million": {"input": 25.0, "output": 150.0},
                    }
                ],
            }
        ]
    }

    snapshot = MODULE.build_snapshot(latest, config, generated_at="2026-09-01T01:00:00+00:00")
    task_profiles = snapshot["routes"][0]["task_profiles"]

    assert task_profiles == {}
    assert snapshot["routes"][0]["scenarios"]["full_economic"]["allocated_cost_per_task_usd"] is None

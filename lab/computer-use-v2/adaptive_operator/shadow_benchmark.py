"""Statistics and fail-closed gates for macOS shadow runs."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PercentileSummary:
    count: int
    minimum: float
    p50: float
    p95: float
    maximum: float


@dataclass(frozen=True)
class ShadowRunMetrics:
    v1_persisted_interval_ms: float
    shadow_cpu_latency_ms: float
    critical_path_overhead_ms: float
    additional_backend_calls: int
    duplicate_backend_observations: int
    v2_device_actions: int
    clicks: int
    keystrokes: int
    focus_changes: int
    screenshots: int
    vision_calls: int
    shadow_errors: int
    shadow_failures_affecting_v1: int


@dataclass(frozen=True)
class ShadowGateResult:
    passed: bool
    failures: tuple[str, ...]


def nearest_rank_summary(values: list[float]) -> PercentileSummary:
    if not values:
        raise ValueError("at least one value is required")
    ordered = sorted(float(value) for value in values)

    def percentile(percent: float) -> float:
        rank = max(1, math.ceil(percent / 100.0 * len(ordered)))
        return ordered[rank - 1]

    return PercentileSummary(
        count=len(ordered),
        minimum=ordered[0],
        p50=percentile(50),
        p95=percentile(95),
        maximum=ordered[-1],
    )


def evaluate_shadow_gates(
    runs: list[ShadowRunMetrics],
    *,
    v1_behavior_changed: bool,
    model_facing_schema_changed: bool,
    v1_production_source_changed: bool,
    lot20_hash_verified: bool,
    v1_release_verified: bool,
    v1_plugin_verified: bool,
) -> ShadowGateResult:
    failures: list[str] = []
    flags = {
        "v1_behavior_changed": v1_behavior_changed,
        "model_facing_schema_changed": model_facing_schema_changed,
        "v1_production_source_changed": v1_production_source_changed,
    }
    failures.extend(name for name, changed in flags.items() if changed)
    integrity = {
        "lot20_hash_verified": lot20_hash_verified,
        "v1_release_verified": v1_release_verified,
        "v1_plugin_verified": v1_plugin_verified,
    }
    failures.extend(name for name, verified in integrity.items() if not verified)
    forbidden_counters = (
        "additional_backend_calls",
        "duplicate_backend_observations",
        "v2_device_actions",
        "clicks",
        "keystrokes",
        "focus_changes",
        "screenshots",
        "vision_calls",
        "shadow_failures_affecting_v1",
    )
    for name in forbidden_counters:
        if sum(int(getattr(run, name)) for run in runs) != 0:
            failures.append(name)
    return ShadowGateResult(passed=not failures, failures=tuple(failures))

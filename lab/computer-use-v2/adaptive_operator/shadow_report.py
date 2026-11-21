"""Aggregation primitives for Lot 2.1 shadow benchmark reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from adaptive_operator.shadow_benchmark import nearest_rank_summary


@dataclass(frozen=True)
class ShadowMeasuredRun:
    scenario_id: str
    v1_persisted_interval_ms: float
    shadow_cpu_latency_ms: float
    compaction_latency_ms: float
    critical_path_overhead_ms: float
    raw_ax_chars: int
    compact_ax_chars: int
    raw_estimated_tokens: int
    compact_estimated_tokens: int
    reduction_percent: float
    information_loss_elements: int
    ref_native: int
    ref_shadow_synthetic: int
    additional_backend_calls: int
    duplicate_backend_observations: int
    v2_errors: int
    device_context_resolution_ms: float = 0.0
    activity_detection_ms: float = 0.0
    observation_conversion_ms: float = 0.0
    policy_classification_ms: float = 0.0
    ref_freshness_loss: int = 0
    ref_freshness_assessable: bool = False


def aggregate_measured_runs(runs: list[ShadowMeasuredRun]) -> dict[str, Any]:
    if not runs:
        raise ValueError("at least one measured run is required")
    percentile_fields = (
        "v1_persisted_interval_ms",
        "shadow_cpu_latency_ms",
        "compaction_latency_ms",
        "critical_path_overhead_ms",
        "raw_ax_chars",
        "compact_ax_chars",
        "raw_estimated_tokens",
        "compact_estimated_tokens",
        "reduction_percent",
        "information_loss_elements",
        "ref_native",
        "ref_shadow_synthetic",
        "device_context_resolution_ms",
        "activity_detection_ms",
        "observation_conversion_ms",
        "policy_classification_ms",
    )
    output: dict[str, Any] = {"run_count": len(runs)}
    for field in percentile_fields:
        output[field] = asdict(
            nearest_rank_summary([float(getattr(run, field)) for run in runs])
        )
    for field in (
        "additional_backend_calls",
        "duplicate_backend_observations",
        "v2_errors",
    ):
        output[field] = sum(int(getattr(run, field)) for run in runs)
    assessable = sum(bool(run.ref_freshness_assessable) for run in runs)
    output["ref_freshness_assessable_runs"] = assessable
    output["ref_freshness_unknown_runs"] = len(runs) - assessable
    output["ref_freshness_loss"] = (
        asdict(
            nearest_rank_summary([
                float(run.ref_freshness_loss)
                for run in runs
                if run.ref_freshness_assessable
            ])
        )
        if assessable
        else None
    )
    return output


def summarize_policy_levels(rows: list[dict[str, Any]]) -> dict[str, int]:
    output = {"L0": 0, "L1": 0, "L2": 0, "unknown": 0}
    for row in rows:
        level = row.get("predicted_level")
        output[level if level in {"L0", "L1", "L2"} else "unknown"] += 1
    return output

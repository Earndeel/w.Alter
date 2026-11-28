from __future__ import annotations

from adaptive_operator.shadow_report import (
    ShadowMeasuredRun,
    aggregate_measured_runs,
    summarize_policy_levels,
)


def test_aggregate_measured_runs_uses_nearest_rank_and_exact_counters():
    runs = [
        ShadowMeasuredRun(
            scenario_id="C",
            v1_persisted_interval_ms=float(value * 10),
            shadow_cpu_latency_ms=float(value),
            compaction_latency_ms=float(value) / 2,
            critical_path_overhead_ms=0.0,
            raw_ax_chars=1000,
            compact_ax_chars=250,
            raw_estimated_tokens=250,
            compact_estimated_tokens=63,
            reduction_percent=75.0,
            information_loss_elements=0,
            ref_native=1,
            ref_shadow_synthetic=0,
            additional_backend_calls=0,
            duplicate_backend_observations=0,
            v2_errors=0,
            ref_freshness_assessable=False,
        )
        for value in range(1, 21)
    ]

    report = aggregate_measured_runs(runs)

    assert report["run_count"] == 20
    assert report["shadow_cpu_latency_ms"] == {
        "count": 20,
        "minimum": 1.0,
        "p50": 10.0,
        "p95": 19.0,
        "maximum": 20.0,
    }
    assert report["additional_backend_calls"] == 0
    assert report["duplicate_backend_observations"] == 0
    assert report["raw_estimated_tokens"]["p50"] == 250.0
    assert report["compact_estimated_tokens"]["p95"] == 63.0
    assert report["compaction_latency_ms"]["p50"] == 5.0
    assert report["device_context_resolution_ms"]["p95"] == 0.0
    assert report["ref_freshness_assessable_runs"] == 0
    assert report["ref_freshness_unknown_runs"] == 20


def test_policy_summary_keeps_unknown_separate_from_l0():
    rows = [
        {"predicted_level": "L0"},
        {"predicted_level": "L1"},
        {"predicted_level": "L2"},
        {"predicted_level": None},
        {"predicted_level": None},
    ]

    summary = summarize_policy_levels(rows)

    assert summary == {"L0": 1, "L1": 1, "L2": 1, "unknown": 2}

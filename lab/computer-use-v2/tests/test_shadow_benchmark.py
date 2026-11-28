from __future__ import annotations

import pytest

from adaptive_operator.shadow_benchmark import (
    ShadowRunMetrics,
    evaluate_shadow_gates,
    nearest_rank_summary,
)


def test_nearest_rank_summary_reports_exact_p50_p95_min_max():
    values = [float(value) for value in range(1, 21)]

    summary = nearest_rank_summary(values)

    assert summary.count == 20
    assert summary.minimum == 1.0
    assert summary.p50 == 10.0
    assert summary.p95 == 19.0
    assert summary.maximum == 20.0


def test_shadow_gates_pass_only_with_no_mutation_duplication_or_v1_impact():
    metrics = ShadowRunMetrics(
        v1_persisted_interval_ms=200.0,
        shadow_cpu_latency_ms=1.0,
        critical_path_overhead_ms=0.0,
        additional_backend_calls=0,
        duplicate_backend_observations=0,
        v2_device_actions=0,
        clicks=0,
        keystrokes=0,
        focus_changes=0,
        screenshots=0,
        vision_calls=0,
        shadow_errors=0,
        shadow_failures_affecting_v1=0,
    )

    result = evaluate_shadow_gates(
        [metrics],
        v1_behavior_changed=False,
        model_facing_schema_changed=False,
        v1_production_source_changed=False,
        lot20_hash_verified=True,
        v1_release_verified=True,
        v1_plugin_verified=True,
    )

    assert result.passed is True
    assert result.failures == ()


@pytest.mark.parametrize(
    ("field", "failure"),
    [
        ("additional_backend_calls", "additional_backend_calls"),
        ("duplicate_backend_observations", "duplicate_backend_observations"),
        ("v2_device_actions", "v2_device_actions"),
        ("clicks", "clicks"),
        ("keystrokes", "keystrokes"),
        ("focus_changes", "focus_changes"),
        ("screenshots", "screenshots"),
        ("vision_calls", "vision_calls"),
        ("shadow_failures_affecting_v1", "shadow_failures_affecting_v1"),
    ],
)
def test_any_forbidden_counter_fails_the_gate(field, failure):
    values = {name: 0 for name in ShadowRunMetrics.__dataclass_fields__}
    values.update(
        v1_persisted_interval_ms=1.0,
        shadow_cpu_latency_ms=1.0,
        critical_path_overhead_ms=0.0,
        shadow_errors=0,
    )
    values[field] = 1

    result = evaluate_shadow_gates(
        [ShadowRunMetrics(**values)],
        v1_behavior_changed=False,
        model_facing_schema_changed=False,
        v1_production_source_changed=False,
        lot20_hash_verified=True,
        v1_release_verified=True,
        v1_plugin_verified=True,
    )

    assert result.passed is False
    assert failure in result.failures

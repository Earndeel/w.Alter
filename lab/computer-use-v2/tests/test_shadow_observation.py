from __future__ import annotations

from adaptive_operator.observation import ObservationDetail
from adaptive_operator.shadow_observation import V1ObservationAdapter
from adaptive_operator.shadow_replay import ShadowReplayEvent


def _capture_event(*, total_elements: int = 3, truncated: int = 0):
    elements = [
        {
            "index": index + 1,
            "role": "AXButton",
            "label": f"Button {index + 1}",
            "bounds": [10 * index, 20, 80, 24],
            "enabled": True,
            **({"element_token": f"native-{index}"} if index == 0 else {}),
        }
        for index in range(3)
    ]
    return ShadowReplayEvent(
        session_id="session-1",
        call_id="call-1",
        action="capture",
        arguments={"action": "capture", "mode": "ax", "app": "Finder"},
        result={
            "mode": "ax",
            "width": 1512,
            "height": 982,
            "app": "Finder",
            "window_title": "Downloads",
            "elements": elements,
            "total_elements": total_elements,
            "truncated_elements": truncated,
        },
        call_message_id=10,
        result_message_id=11,
        called_at=100.0,
        completed_at=100.2,
    )


def test_v1_capture_becomes_generation_bound_compact_observation_with_metrics():
    converted = V1ObservationAdapter(device_id="mac-configured", max_elements=2).convert(
        _capture_event(), detail=ObservationDetail.RELEVANT
    )

    assert converted.observation.snapshot_id == "session-1:11"
    assert converted.observation.generation == 11
    assert converted.observation.app == "Finder"
    assert converted.observation.window == "Downloads"
    assert len(converted.observation.elements) == 2
    assert all(ref.ref.startswith("e11-") for ref in converted.observation.elements)
    assert converted.metrics.raw_ax_chars > converted.metrics.compact_ax_chars
    assert converted.metrics.raw_estimated_tokens >= converted.metrics.compact_estimated_tokens
    assert converted.metrics.reduction_percent > 0
    assert converted.metrics.compaction_latency_ms >= 0
    assert converted.metrics.ref_native == 1
    assert converted.metrics.ref_shadow_synthetic == 2
    assert converted.metrics.information_loss_elements == 1
    assert converted.metrics.additional_backend_calls == 0


def test_truncated_v1_capture_reports_source_loss_and_never_makes_synthetic_ref_actionable():
    converted = V1ObservationAdapter(device_id="mac-configured", max_elements=10).convert(
        _capture_event(total_elements=8, truncated=5), detail=ObservationDetail.DETAILED
    )

    assert converted.metrics.source_truncated_elements == 5
    assert converted.metrics.information_loss_elements == 5
    assert converted.metrics.ref_shadow_synthetic == 2
    synthetic = [item for item in converted.observation.elements if item.ref_integrity == "shadow_synthetic"]
    assert synthetic
    assert all(item.actionable is False for item in synthetic)

from __future__ import annotations

from adaptive_operator.device_context import (
    DeviceContextStore,
    DisplayProfile,
)
from adaptive_operator.macos_shadow import LocalMacContextSource
from adaptive_operator.shadow_context import apply_v1_capture_context
from adaptive_operator.shadow_replay import ShadowReplayEvent


def _event(result):
    return ShadowReplayEvent(
        session_id="s",
        call_id="c",
        action="capture",
        arguments={"action": "capture", "mode": "ax"},
        result=result,
        call_message_id=1,
        result_message_id=2,
        called_at=1.0,
        completed_at=2.0,
    )


def test_v1_capture_updates_runtime_context_without_device_call_or_fake_geometry(tmp_path):
    store = DeviceContextStore(tmp_path / "context.json")
    store.upsert(LocalMacContextSource.synthetic_for_test(device_id="mac", now=1.0))

    updated = apply_v1_capture_context(
        store,
        device_id="mac",
        event=_event(
            {
                "app": "Finder",
                "width": 0,
                "height": 0,
                "elements": [{"role": "button", "label": "Open"}],
                "capture_valid": False,
                "capture_error": {"code": "desktop_escalation_required"},
            }
        ),
    )

    assert updated.profile.displays == ()
    assert updated.profile.accessibility.available is True
    assert updated.activity.foreground_app == "Finder"
    assert updated.health.cua_driver == "degraded:desktop_escalation_required"
    assert updated.source_device_calls == 0


def test_positive_v1_dimensions_are_preserved_with_unknown_scale(tmp_path):
    store = DeviceContextStore(tmp_path / "context.json")
    store.upsert(LocalMacContextSource.synthetic_for_test(device_id="mac", now=1.0))

    updated = apply_v1_capture_context(
        store,
        device_id="mac",
        event=_event({"width": 1512, "height": 982, "elements": []}),
    )

    assert updated.profile.displays == (
        DisplayProfile(display_id="v1-target", width_px=1512, height_px=982, scale=None),
    )

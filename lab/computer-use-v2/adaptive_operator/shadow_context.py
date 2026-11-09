"""Merge already-observed V1 capture facts into the shadow DeviceContext."""

from __future__ import annotations

from dataclasses import replace

from adaptive_operator.device_context import (
    AccessibilityState,
    DeviceActivity,
    DeviceContextStore,
    DeviceHealth,
    DisplayProfile,
)
from adaptive_operator.shadow_replay import ShadowReplayEvent


def apply_v1_capture_context(
    store: DeviceContextStore,
    *,
    device_id: str,
    event: ShadowReplayEvent,
):
    current = store.get(device_id)
    if current is None:
        raise LookupError(f"unknown device {device_id!r}")
    if event.action != "capture" or not isinstance(event.result, dict):
        raise ValueError("a persisted V1 capture is required")
    result = event.result
    width = _positive_int(result.get("width"))
    height = _positive_int(result.get("height"))
    displays = current.profile.displays
    if width is not None and height is not None:
        displays = (
            DisplayProfile(
                display_id="v1-target",
                width_px=width,
                height_px=height,
                scale=None,
            ),
        )
    elements = result.get("elements")
    accessibility = current.profile.accessibility
    if isinstance(elements, list):
        accessibility = AccessibilityState(available=True, provider="v1_ax_payload")
    capture_valid = result.get("capture_valid")
    error = result.get("capture_error")
    code = error.get("code") if isinstance(error, dict) else None
    if capture_valid is False:
        driver_health = f"degraded:{code or 'capture_invalid'}"
    elif capture_valid is True:
        driver_health = "healthy"
    else:
        driver_health = "unknown"
    observed_at = event.completed_at
    previous_activity = current.activity
    activity = DeviceActivity(
        observed_at=observed_at,
        screen_locked=(previous_activity.screen_locked if previous_activity else None),
        foreground_app=_optional_text(result.get("app")),
        idle_seconds=(previous_activity.idle_seconds if previous_activity else None),
        recent_input=(previous_activity.recent_input if previous_activity else None),
        recent_keyboard=(previous_activity.recent_keyboard if previous_activity else None),
        recent_pointer=(previous_activity.recent_pointer if previous_activity else None),
    )
    candidate = replace(
        current,
        profile=replace(
            current.profile,
            displays=displays,
            accessibility=accessibility,
        ),
        activity=activity,
        health=DeviceHealth(observed_at=observed_at, cua_driver=driver_health),
        sources=("v1_capture_replay",),
        source_device_calls=0,
    )
    return store.upsert(candidate)


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _optional_text(value):
    text = str(value).strip() if value is not None else ""
    return text or None

"""Non-enforcing interruption predictions for persisted V1 actions."""

from __future__ import annotations

from dataclasses import dataclass

from adaptive_operator.device_context import DeviceActivity
from adaptive_operator.interruption import (
    ActionEffects,
    InterruptionLevel,
)
from adaptive_operator.shadow_replay import ShadowReplayEvent


_READ_ONLY = {
    "capture",
    "wait",
    "list_apps",
    "list_windows",
    "cua_browser_state",
    "status",
    "inspect",
    "verify_state",
}
_INPUT = {
    "click",
    "double_click",
    "right_click",
    "middle_click",
    "drag",
    "scroll",
    "type",
    "key",
    "set_value",
    "cua_browser_click",
    "cua_browser_type",
    "cua_browser_pointer",
    "cua_browser_set_input_files",
    "cua_browser_download",
}
_VISIBLE = {"launch_app", "open_url", "cua_browser_navigate", "cua_browser_prepare"}
_DESTRUCTIVE = {"kill_app"}
_DESTRUCTIVE_KEYS = {
    "cmd+q",
    "command+q",
    "alt+f4",
    "cmd+w",
    "command+w",
}


@dataclass(frozen=True)
class ShadowInterruptionPrediction:
    predicted_level: InterruptionLevel | None
    observed_effects: ActionEffects
    would_warn: bool
    would_confirm: bool
    user_active: bool | None
    classification_status: str = "observed"
    reason: str | None = None
    enforced: bool = False
    blocked_v1: bool = False


class ShadowInterruptionClassifier:
    """Predict policy outcomes without warning, confirming, or blocking V1."""

    def classify(
        self,
        event: ShadowReplayEvent,
        *,
        activity: DeviceActivity | None,
    ) -> ShadowInterruptionPrediction:
        if event.action == "goal":
            return ShadowInterruptionPrediction(
                predicted_level=None,
                observed_effects=ActionEffects(),
                would_warn=False,
                would_confirm=False,
                user_active=activity.user_active if activity is not None else None,
                classification_status="unknown",
                reason="opaque composite action has no atomic effects",
            )
        effects = self.effects(event)
        level = effects.level()
        return ShadowInterruptionPrediction(
            predicted_level=level,
            observed_effects=effects,
            would_warn=level is InterruptionLevel.L1_WARN,
            would_confirm=level is InterruptionLevel.L2_CONFIRM,
            user_active=activity.user_active if activity is not None else None,
        )

    @staticmethod
    def effects(event: ShadowReplayEvent) -> ActionEffects:
        action = event.action or ""
        arguments = event.arguments
        if action in _READ_ONLY:
            return ActionEffects(read_only=True)
        if action in _DESTRUCTIVE:
            return ActionEffects(
                visible_ui=True,
                desktop_change=True,
                destructive=True,
                closes_unsaved_work=True,
            )
        if action == "focus_app":
            raised = bool(arguments.get("raise_window"))
            return ActionEffects(
                read_only=not raised,
                visible_ui=raised,
                focus_change=raised,
            )
        if action == "key":
            keys = str(arguments.get("keys") or "").strip().casefold()
            if keys in _DESTRUCTIVE_KEYS:
                return ActionEffects(
                    keyboard=True,
                    visible_ui=True,
                    closes_unsaved_work=True,
                    destructive=True,
                )
            return ActionEffects(keyboard=True, visible_ui=True)
        if action in _INPUT:
            return ActionEffects(
                visible_ui=True,
                pointer=action in {"click", "double_click", "right_click", "middle_click", "drag", "scroll", "cua_browser_click", "cua_browser_pointer"},
                keyboard=action in {"type", "key", "set_value", "cua_browser_type"},
                desktop_change=True,
            )
        if action in _VISIBLE:
            return ActionEffects(visible_ui=True, desktop_change=True)
        return ActionEffects(read_only=False)

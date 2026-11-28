from __future__ import annotations

import pytest

from adaptive_operator.device_context import DeviceActivity
from adaptive_operator.shadow_policy import ShadowInterruptionClassifier
from adaptive_operator.shadow_replay import ShadowReplayEvent


def _event(action: str, arguments: dict | None = None, result: dict | None = None):
    return ShadowReplayEvent(
        session_id="s",
        call_id=f"call-{action}",
        action=action,
        arguments={"action": action, **(arguments or {})},
        result=result or {},
        call_message_id=1,
        result_message_id=2,
        called_at=1.0,
        completed_at=2.0,
    )


@pytest.mark.parametrize(
    ("event", "level", "warn", "confirm"),
    [
        (_event("capture", {"mode": "ax"}), "L0", False, False),
        (_event("list_windows"), "L0", False, False),
        (_event("verify_state"), "L0", False, False),
        (_event("focus_app", {"raise_window": False}), "L0", False, False),
        (_event("focus_app", {"raise_window": True}), "L1", True, False),
        (_event("type", {"text": "hello"}), "L1", True, False),
        (_event("launch_app", {"name": "Safari"}), "L1", True, False),
        (_event("key", {"keys": "cmd+q"}), "L2", False, True),
        (_event("kill_app", {"name": "Example"}), "L2", False, True),
    ],
)
def test_shadow_classifies_v1_action_without_enforcement(event, level, warn, confirm):
    prediction = ShadowInterruptionClassifier().classify(event, activity=None)

    assert prediction.predicted_level.value == level
    assert prediction.would_warn is warn
    assert prediction.would_confirm is confirm
    assert prediction.enforced is False
    assert prediction.blocked_v1 is False


def test_active_user_visible_action_warns_but_background_read_does_not():
    active = DeviceActivity(
        observed_at=10.0,
        screen_locked=False,
        foreground_app="Finder",
        idle_seconds=1.0,
        recent_keyboard=True,
        recent_pointer=None,
    )
    classifier = ShadowInterruptionClassifier()

    visible = classifier.classify(_event("launch_app", {"name": "Safari"}), activity=active)
    background = classifier.classify(_event("capture", {"mode": "ax"}), activity=active)

    assert visible.user_active is True
    assert visible.would_warn is True
    assert background.user_active is True
    assert background.would_warn is False


def test_opaque_goal_is_reported_unknown_instead_of_inventing_effects():
    prediction = ShadowInterruptionClassifier().classify(
        _event("goal", {"goal": "opaque composite task"}), activity=None
    )

    assert prediction.predicted_level is None
    assert prediction.classification_status == "unknown"
    assert prediction.reason == "opaque composite action has no atomic effects"
    assert prediction.would_warn is False
    assert prediction.would_confirm is False

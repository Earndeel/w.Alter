from __future__ import annotations

import pytest

from adaptive_operator.interruption import (
    ActionEffects,
    EnforcementEvidence,
    InterruptionGate,
    InterruptionLevel,
    PolicyBlocked,
    RuntimeEvidenceLedger,
)
from adaptive_operator.device_context import DeviceActivity


SCOPE = "task-1:step-1"
DEVICE = "mac-main"
NOW = 100.0


def test_l0_read_state_is_silent_and_needs_no_evidence():
    gate = InterruptionGate(RuntimeEvidenceLedger())

    decision = gate.authorize(
        ActionEffects(read_only=True),
        activity=None,
        evidence=EnforcementEvidence(),
        action_scope=SCOPE,
        device_id=DEVICE,
        now=NOW,
    )

    assert decision.level is InterruptionLevel.L0_SILENT
    assert decision.allowed is True
    assert decision.warning_required is False
    assert decision.confirmation_required is False


def test_l1_requires_runtime_warning_receipt_scoped_to_action_and_device():
    ledger = RuntimeEvidenceLedger()
    gate = InterruptionGate(ledger)
    activity = DeviceActivity(
        observed_at=10.0,
        screen_locked=False,
        foreground_app="Editor",
        idle_seconds=1.0,
        recent_keyboard=True,
        recent_pointer=False,
    )
    effects = ActionEffects(visible_ui=True, focus_change=True, keyboard=True)

    with pytest.raises(PolicyBlocked) as blocked:
        gate.authorize(
            effects,
            activity=activity,
            evidence=EnforcementEvidence(),
            action_scope=SCOPE,
            device_id=DEVICE,
            now=NOW,
        )
    assert blocked.value.code == "interruption_warning_required"

    receipt = ledger.record_warning(
        action_scope=SCOPE, device_id=DEVICE, now=NOW, ttl_seconds=10
    )
    decision = gate.authorize(
        effects,
        activity=activity,
        evidence=EnforcementEvidence(warning_receipt_id=receipt),
        action_scope=SCOPE,
        device_id=DEVICE,
        now=NOW + 1,
    )
    assert decision.level is InterruptionLevel.L1_WARN
    assert decision.allowed is True
    assert decision.user_active is True

    with pytest.raises(PolicyBlocked) as replayed:
        gate.authorize(
            effects,
            activity=activity,
            evidence=EnforcementEvidence(warning_receipt_id=receipt),
            action_scope=SCOPE,
            device_id=DEVICE,
            now=NOW + 2,
        )
    assert replayed.value.code == "interruption_warning_required"


def test_warning_receipt_is_fail_closed_for_wrong_scope_device_or_expiry():
    for scope, device, now in (
        ("other-step", DEVICE, NOW + 1),
        (SCOPE, "other-device", NOW + 1),
        (SCOPE, DEVICE, NOW + 11),
    ):
        ledger = RuntimeEvidenceLedger()
        receipt = ledger.record_warning(
            action_scope=SCOPE, device_id=DEVICE, now=NOW, ttl_seconds=10
        )
        with pytest.raises(PolicyBlocked):
            InterruptionGate(ledger).authorize(
                ActionEffects(pointer=True),
                activity=None,
                evidence=EnforcementEvidence(warning_receipt_id=receipt),
                action_scope=scope,
                device_id=device,
                now=now,
            )


def test_l2_requires_scoped_runtime_confirmation_grant():
    ledger = RuntimeEvidenceLedger()
    gate = InterruptionGate(ledger)
    effects = ActionEffects(destructive=True, irreversible=True)

    warning = ledger.record_warning(
        action_scope=SCOPE, device_id=DEVICE, now=NOW, ttl_seconds=10
    )
    with pytest.raises(PolicyBlocked) as blocked:
        gate.authorize(
            effects,
            activity=None,
            evidence=EnforcementEvidence(warning_receipt_id=warning),
            action_scope=SCOPE,
            device_id=DEVICE,
            now=NOW,
        )
    assert blocked.value.code == "interruption_confirmation_required"

    grant = ledger.record_confirmation(
        action_scope=SCOPE, device_id=DEVICE, now=NOW, ttl_seconds=10
    )
    decision = gate.authorize(
        effects,
        activity=None,
        evidence=EnforcementEvidence(confirmation_grant_id=grant),
        action_scope=SCOPE,
        device_id=DEVICE,
        now=NOW + 1,
    )
    assert decision.level is InterruptionLevel.L2_CONFIRM
    assert decision.allowed is True


def test_locked_screen_blocks_visible_or_foreground_input_even_with_receipt():
    ledger = RuntimeEvidenceLedger()
    receipt = ledger.record_warning(
        action_scope=SCOPE, device_id=DEVICE, now=NOW, ttl_seconds=10
    )
    locked = DeviceActivity(observed_at=5.0, screen_locked=True)

    with pytest.raises(PolicyBlocked) as blocked:
        InterruptionGate(ledger).authorize(
            ActionEffects(visible_ui=True, focus_change=True),
            activity=locked,
            evidence=EnforcementEvidence(warning_receipt_id=receipt),
            action_scope=SCOPE,
            device_id=DEVICE,
            now=NOW,
        )

    assert blocked.value.code == "screen_locked_visible_action_refused"

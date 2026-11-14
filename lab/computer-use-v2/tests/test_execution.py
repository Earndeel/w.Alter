from __future__ import annotations

import pytest

from adaptive_operator.execution import (
    ActionOutcome,
    ActionStatus,
    ExecutionEngine,
    ExecutionStep,
    VerificationKind,
    VerificationSpec,
)
from adaptive_operator.capabilities import (
    CapabilityOffer,
    CapabilityProvider,
    CostEstimate,
    Primitive,
)
from adaptive_operator.interruption import (
    ActionEffects,
    EnforcementEvidence,
    InterruptionGate,
    PolicyBlocked,
    RuntimeEvidenceLedger,
)


def _offer(effects: ActionEffects = ActionEffects()) -> CapabilityOffer:
    return CapabilityOffer(
        offer_id="native-launch",
        primitive=Primitive.LAUNCH_APP,
        provider=CapabilityProvider.COMPUTER_USE,
        confidence=0.99,
        cost=CostEstimate(50, 0, 1, 0, 0.01),
        effects=effects,
    )


def test_engine_executes_one_llm_selected_step_then_uses_deterministic_verifier():
    calls = []

    def dispatch(step: ExecutionStep):
        calls.append(step)
        return {"transport_ok": True, "pid": 12, "window_id": 34}

    def observe(step: ExecutionStep, result):
        assert result["pid"] == 12
        return {"window_exists": True, "snapshot": "s2"}

    engine = ExecutionEngine(
        gate=InterruptionGate(RuntimeEvidenceLedger()),
        dispatch=dispatch,
        observe=observe,
    )
    step = ExecutionStep(
        step_id="s1",
        device_id="mac-main",
        offer=_offer(),
        arguments={"app": "Browser"},
        verify=VerificationSpec(VerificationKind.PREDICATE, {"window_exists": True}),
    )

    outcome = engine.execute(step, evidence=EnforcementEvidence())

    assert outcome.status is ActionStatus.CONFIRMED
    assert outcome.completion_known is True
    assert outcome.adaptation_required is False
    assert outcome.observation == {"window_exists": True, "snapshot": "s2"}
    assert calls == [step]


def test_failed_verification_returns_evidence_to_llm_without_runtime_recipe_loop():
    engine = ExecutionEngine(
        gate=InterruptionGate(RuntimeEvidenceLedger()),
        dispatch=lambda step: {"transport_ok": True},
        observe=lambda step, result: {"window_exists": False},
    )
    step = ExecutionStep(
        step_id="s1",
        device_id="mac-main",
        offer=_offer(),
        arguments={},
        verify=VerificationSpec(VerificationKind.PREDICATE, {"window_exists": True}),
    )

    outcome = engine.execute(step, evidence=EnforcementEvidence())

    assert outcome.status is ActionStatus.UNVERIFIABLE
    assert outcome.completion_known is False
    assert outcome.adaptation_required is True
    assert outcome.next_authority == "llm"
    assert outcome.automatic_retry_performed is False


def test_policy_blocks_dispatch_before_side_effect():
    dispatched = False

    def dispatch(step):
        nonlocal dispatched
        dispatched = True
        return {}

    engine = ExecutionEngine(
        gate=InterruptionGate(RuntimeEvidenceLedger()),
        dispatch=dispatch,
        observe=lambda step, result: {},
    )
    step = ExecutionStep(
        step_id="s1",
        device_id="mac-main",
        offer=_offer(ActionEffects(visible_ui=True, focus_change=True)),
        arguments={},
        verify=VerificationSpec(VerificationKind.NONE),
    )

    with pytest.raises(PolicyBlocked):
        engine.execute(step, evidence=EnforcementEvidence())

    assert dispatched is False


def test_deterministic_driver_proof_avoids_post_action_observation():
    observations = []

    def observe(step, transport):
        observations.append((step, transport))
        return {"unexpected": True}

    engine = ExecutionEngine(
        gate=InterruptionGate(RuntimeEvidenceLedger()),
        dispatch=lambda step: {
            "transport_ok": True,
            "effect": "confirmed",
            "verified": True,
            "verification": {"source": "native_process_state"},
        },
        observe=observe,
    )
    step = ExecutionStep(
        step_id="s1",
        device_id="mac-main",
        offer=_offer(),
        arguments={},
        verify=VerificationSpec(VerificationKind.DETERMINISTIC),
    )
    outcome = engine.execute(step, evidence=EnforcementEvidence())
    assert outcome.status is ActionStatus.CONFIRMED
    assert outcome.verification["source"] == "native_process_state"
    assert observations == []

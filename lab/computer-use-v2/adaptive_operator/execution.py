"""Single-step execution boundary for Act → Observe → Verify → Adapt."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable

from adaptive_operator.capabilities import CapabilityOffer
from adaptive_operator.device_context import DeviceActivity
from adaptive_operator.interruption import EnforcementEvidence, InterruptionGate


class VerificationKind(StrEnum):
    NONE = "none"
    DETERMINISTIC = "deterministic"
    PREDICATE = "predicate"
    DIFF = "diff"
    SEMANTIC = "semantic"


class ActionStatus(StrEnum):
    CONFIRMED = "confirmed"
    UNVERIFIABLE = "unverifiable"
    REFUSED = "refused"
    ERROR = "error"


@dataclass(frozen=True)
class VerificationSpec:
    kind: VerificationKind
    expected: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExecutionStep:
    step_id: str
    device_id: str
    offer: CapabilityOffer
    arguments: dict[str, Any]
    verify: VerificationSpec


@dataclass(frozen=True)
class ActionOutcome:
    status: ActionStatus
    completion_known: bool
    transport: dict[str, Any]
    observation: dict[str, Any]
    verification: dict[str, Any]
    adaptation_required: bool
    next_authority: str = "llm"
    automatic_retry_performed: bool = False


Dispatcher = Callable[[ExecutionStep], dict[str, Any]]
Observer = Callable[[ExecutionStep, dict[str, Any]], dict[str, Any]]


class ExecutionEngine:
    """Executes one LLM-selected offer; never invents a recipe or hidden loop."""

    def __init__(self, *, gate: InterruptionGate, dispatch: Dispatcher, observe: Observer) -> None:
        self.gate = gate
        self.dispatch = dispatch
        self.observe = observe

    def execute(
        self,
        step: ExecutionStep,
        *,
        evidence: EnforcementEvidence,
        activity: DeviceActivity | None = None,
        now: float = 0.0,
    ) -> ActionOutcome:
        self.gate.authorize(
            step.offer.effects,
            activity=activity,
            evidence=evidence,
            action_scope=step.step_id,
            device_id=step.device_id,
            now=now,
        )
        transport = self.dispatch(step)
        if transport.get("transport_ok") is False:
            return ActionOutcome(
                status=ActionStatus.ERROR,
                completion_known=True,
                transport=transport,
                observation={},
                verification={"satisfied": False, "source": "transport"},
                adaptation_required=True,
            )
        if (
            step.verify.kind is VerificationKind.DETERMINISTIC
            and transport.get("verified") is True
            and transport.get("effect") == "confirmed"
        ):
            proof = dict(transport.get("verification") or {})
            proof["satisfied"] = True
            proof.setdefault("source", "driver")
            return ActionOutcome(
                status=ActionStatus.CONFIRMED,
                completion_known=True,
                transport=transport,
                observation={},
                verification=proof,
                adaptation_required=False,
            )
        observation = self.observe(step, transport)
        verification = self._verify(step.verify, observation)
        satisfied = verification["satisfied"] is True
        return ActionOutcome(
            status=ActionStatus.CONFIRMED if satisfied else ActionStatus.UNVERIFIABLE,
            completion_known=satisfied,
            transport=transport,
            observation=observation,
            verification=verification,
            adaptation_required=not satisfied,
        )

    @staticmethod
    def _verify(spec: VerificationSpec, observation: dict[str, Any]) -> dict[str, Any]:
        if spec.kind is VerificationKind.NONE:
            return {"satisfied": True, "source": "no_postcondition_requested"}
        if spec.kind is VerificationKind.PREDICATE:
            expected = spec.expected or {}
            matched = all(observation.get(key) == value for key, value in expected.items())
            return {
                "satisfied": matched,
                "source": "deterministic_predicate",
                "expected": expected,
            }
        return {
            "satisfied": False,
            "source": "higher_order_verifier_required",
            "kind": spec.kind.value,
        }

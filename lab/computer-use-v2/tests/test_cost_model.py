from __future__ import annotations

from adaptive_operator.capabilities import (
    CapabilityOffer,
    CapabilityProvider,
    CapabilityQuery,
    CapabilityRegistry,
    CostEstimate,
    CostWeights,
    Primitive,
)
from adaptive_operator.interruption import ActionEffects


def test_cost_weights_are_configurable_and_not_a_fixed_hidden_policy() -> None:
    cost = CostEstimate(
        latency_ms=1000,
        token_cost=2,
        interaction_cost=3,
        disruption=4,
        failure_risk=5,
    )
    assert cost.score(CostWeights(
        latency=1,
        token=1,
        interaction=1,
        disruption=1,
        failure_risk=1,
    )) == 15
    assert cost.score(CostWeights(
        latency=0,
        token=0,
        interaction=0,
        disruption=10,
        failure_risk=0,
    )) == 40


def test_registry_injected_weights_change_advisory_order_without_selecting() -> None:
    def offer(name: str, *, latency_ms: float, disruption: float) -> CapabilityOffer:
        return CapabilityOffer(
            offer_id=name,
            primitive=Primitive.OBSERVE,
            provider=CapabilityProvider.COMPUTER_USE,
            confidence=0.9,
            cost=CostEstimate(latency_ms, 0, 0, disruption, 0),
            effects=ActionEffects(read_only=True),
        )

    latency_first = CapabilityRegistry(
        [offer("fast-visible", latency_ms=10, disruption=1), offer("slow-silent", latency_ms=1000, disruption=0)],
        cost_weights=CostWeights(latency=10, token=0, interaction=0, disruption=0, failure_risk=0),
    ).catalog(query=CapabilityQuery())
    silent_first = CapabilityRegistry(
        [offer("fast-visible", latency_ms=10, disruption=1), offer("slow-silent", latency_ms=1000, disruption=0)],
        cost_weights=CostWeights(latency=0, token=0, interaction=0, disruption=10, failure_risk=0),
    ).catalog(query=CapabilityQuery())

    assert [item.offer_id for item in latency_first.offers] == ["fast-visible", "slow-silent"]
    assert [item.offer_id for item in silent_first.offers] == ["slow-silent", "fast-visible"]
    assert latency_first.selection_authority == silent_first.selection_authority == "llm"

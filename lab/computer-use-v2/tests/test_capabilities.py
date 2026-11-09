from __future__ import annotations

from adaptive_operator.capabilities import (
    CapabilityOffer,
    CapabilityProvider,
    CapabilityQuery,
    CapabilityRegistry,
    CostEstimate,
    Primitive,
)
from adaptive_operator.interruption import ActionEffects, InterruptionLevel


def _offer(
    name: str,
    primitive: Primitive,
    confidence: float,
    *,
    latency: float,
    disruption: float = 0.0,
    risk: float = 0.0,
    provider: CapabilityProvider = CapabilityProvider.COMPUTER_USE,
) -> CapabilityOffer:
    return CapabilityOffer(
        offer_id=name,
        primitive=primitive,
        provider=provider,
        confidence=confidence,
        cost=CostEstimate(
            latency_ms=latency,
            token_cost=0.0,
            interaction_cost=1.0,
            disruption=disruption,
            failure_risk=risk,
        ),
        effects=ActionEffects(visible_ui=disruption > 0, focus_change=disruption > 0),
        preconditions=("device.connected",),
    )


def test_catalog_filters_below_confidence_and_exposes_cost_without_executing():
    registry = CapabilityRegistry(
        [
            _offer("native-launch", Primitive.LAUNCH_APP, 0.99, latency=80, disruption=0.3),
            _offer("vision-guess", Primitive.VISUAL_CLICK, 0.30, latency=800, risk=0.8),
        ]
    )

    catalog = registry.catalog(
        CapabilityQuery(primitives=(Primitive.LAUNCH_APP, Primitive.VISUAL_CLICK), minimum_confidence=0.75)
    )

    assert [item.offer_id for item in catalog.offers] == ["native-launch"]
    assert catalog.executed is False
    assert catalog.offers[0].interruption_level is InterruptionLevel.L1_WARN
    assert catalog.offers[0].cost.total > 0


def test_ranking_is_advisory_and_cost_weighted_not_a_rigid_native_ax_vision_ladder():
    registry = CapabilityRegistry(
        [
            _offer("visual-fast", Primitive.VISUAL_LOCATE, 0.95, latency=50, risk=0.1),
            _offer("ax-slow", Primitive.INVOKE, 0.95, latency=400, risk=0.1),
        ]
    )

    catalog = registry.catalog(CapabilityQuery(minimum_confidence=0.9))

    assert [item.offer_id for item in catalog.offers] == ["visual-fast", "ax-slow"]
    assert catalog.selection_authority == "llm"


def test_web_information_is_an_external_walter_browse_offer_not_a_computer_use_primitive():
    offer = _offer(
        "research-docs",
        Primitive.RESEARCH,
        0.9,
        latency=500,
        provider=CapabilityProvider.WALTER_BROWSE,
    )
    registry = CapabilityRegistry([offer])

    catalog = registry.catalog(CapabilityQuery(primitives=(Primitive.RESEARCH,)))

    assert catalog.offers[0].provider is CapabilityProvider.WALTER_BROWSE
    assert catalog.offers[0].dispatch_boundary == "external_front_door"
    assert Primitive.RESEARCH not in Primitive.computer_use_runtime_primitives()


def test_unknown_goal_has_observation_offer_instead_of_unsupported_goal():
    registry = CapabilityRegistry(
        [_offer("observe-current", Primitive.OBSERVE, 1.0, latency=40)]
    )

    catalog = registry.catalog(CapabilityQuery(goal="unfamiliar application task"))

    assert catalog.status == "needs_reasoning"
    assert catalog.offers[0].primitive is Primitive.OBSERVE

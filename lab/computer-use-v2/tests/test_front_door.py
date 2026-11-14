from __future__ import annotations

import pytest

from adaptive_operator.capabilities import (
    CapabilityOffer,
    CapabilityProvider,
    CapabilityRegistry,
    CostEstimate,
    Primitive,
)
from adaptive_operator.front_door import (
    ActRequest,
    ComputerUseV2,
    InspectRequest,
    Operation,
    StatusRequest,
)
from adaptive_operator.interruption import ActionEffects


def offer(offer_id: str, primitive: Primitive, provider: CapabilityProvider) -> CapabilityOffer:
    return CapabilityOffer(
        offer_id=offer_id,
        primitive=primitive,
        provider=provider,
        confidence=0.91,
        cost=CostEstimate(20, 0, 0, 0, 0.05),
        effects=ActionEffects(read_only=primitive is Primitive.OBSERVE),
    )


def test_front_door_has_three_operations_not_one_tool_per_primitive() -> None:
    assert tuple(Operation) == (Operation.INSPECT, Operation.ACT, Operation.STATUS)


def test_unknown_goal_returns_reasoning_surface_not_unsupported_goal() -> None:
    runtime = ComputerUseV2(
        CapabilityRegistry([
            offer("observe.minimal", Primitive.OBSERVE, CapabilityProvider.COMPUTER_USE),
            offer("research.external", Primitive.RESEARCH, CapabilityProvider.WALTER_BROWSE),
        ])
    )
    response = runtime.inspect(InspectRequest(device_id="d1", goal="do something unfamiliar"))
    assert response["status"] == "needs_reasoning"
    assert response["selection_authority"] == "llm"
    assert {item["provider"] for item in response["offers"]} == {"computer_use", "walter_browse"}
    assert response["executed"] is False


def test_computer_use_refuses_to_dispatch_external_walter_browse_offer() -> None:
    runtime = ComputerUseV2(
        CapabilityRegistry([
            offer("research.external", Primitive.RESEARCH, CapabilityProvider.WALTER_BROWSE),
        ])
    )
    with pytest.raises(ValueError, match="external front door"):
        runtime.prepare_act(ActRequest(
            device_id="d1",
            offer_id="research.external",
            arguments={"query": "documentation"},
            verify={"kind": "none"},
        ))


def test_act_resolves_exact_offer_without_planning_or_auto_execution() -> None:
    runtime = ComputerUseV2(
        CapabilityRegistry([
            offer("ax.invoke", Primitive.INVOKE, CapabilityProvider.COMPUTER_USE),
        ])
    )
    prepared = runtime.prepare_act(ActRequest(
        device_id="d1",
        offer_id="ax.invoke",
        arguments={"ref": "e2-deadbeef"},
        verify={"kind": "predicate", "expected": {"selected": True}},
    ))
    assert prepared["offer_id"] == "ax.invoke"
    assert prepared["primitive"] == "invoke"
    assert prepared["selection_authority"] == "llm"
    assert prepared["executed"] is False


def test_status_reads_only_through_injected_operation_reader() -> None:
    seen = []

    def reader(request: StatusRequest):
        seen.append(request)
        return {"operation_id": request.operation_id, "status": "succeeded"}

    request = StatusRequest(device_id="d1", operation_id="op-7")
    runtime = ComputerUseV2(CapabilityRegistry([]), status_reader=reader)
    assert runtime.status(request) == {"operation_id": "op-7", "status": "succeeded"}
    assert seen == [request]

    with pytest.raises(RuntimeError, match="status reader"):
        ComputerUseV2(CapabilityRegistry([])).status(request)


def test_snapshot_bound_offer_refuses_missing_or_stale_snapshot() -> None:
    bound = CapabilityOffer(
        offer_id="ax.current",
        primitive=Primitive.INVOKE,
        provider=CapabilityProvider.COMPUTER_USE,
        confidence=0.99,
        cost=CostEstimate(10, 0, 0, 0, 0),
        effects=ActionEffects(read_only=True),
        preconditions=("snapshot:s18",),
    )
    runtime = ComputerUseV2(
        CapabilityRegistry([bound]),
        snapshot_reader=lambda device_id: "s18",
    )
    with pytest.raises(ValueError, match="current snapshot"):
        runtime.prepare_act(ActRequest(
            device_id="d1",
            offer_id="ax.current",
            arguments={"ref": "e18-deadbeef"},
            verify={"kind": "predicate"},
            snapshot_id="s17",
        ))
    prepared = runtime.prepare_act(ActRequest(
        device_id="d1",
        offer_id="ax.current",
        arguments={"ref": "e18-deadbeef"},
        verify={"kind": "predicate"},
        snapshot_id="s18",
    ))
    assert prepared["snapshot_id"] == "s18"

    with pytest.raises(RuntimeError, match="snapshot reader"):
        ComputerUseV2(CapabilityRegistry([bound])).prepare_act(ActRequest(
            device_id="d1",
            offer_id="ax.current",
            arguments={"ref": "e18-deadbeef"},
            verify={"kind": "predicate"},
            snapshot_id="s18",
        ))


def test_status_is_a_protocol_contract_not_hidden_polling() -> None:
    request = StatusRequest(device_id="d1", operation_id="op-7")
    assert request.operation is Operation.STATUS

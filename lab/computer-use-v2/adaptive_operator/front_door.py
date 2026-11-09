"""Single model-facing Computer Use V2 protocol.

The LLM chooses an offer. This façade exposes compact evidence and validates one
chosen action; it does not plan, browse, retry, or dispatch external providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable

from adaptive_operator.capabilities import (
    CapabilityProvider,
    CapabilityQuery,
    CapabilityRegistry,
)


class Operation(StrEnum):
    INSPECT = "inspect"
    ACT = "act"
    STATUS = "status"


@dataclass(frozen=True)
class InspectRequest:
    device_id: str
    goal: str | None = None
    operation: Operation = Operation.INSPECT


@dataclass(frozen=True)
class ActRequest:
    device_id: str
    offer_id: str
    arguments: dict[str, Any]
    verify: dict[str, Any]
    snapshot_id: str | None = None
    operation: Operation = Operation.ACT


@dataclass(frozen=True)
class StatusRequest:
    device_id: str
    operation_id: str
    operation: Operation = Operation.STATUS


class ComputerUseV2:
    """Protocol adapter; a later lot wires this to the existing computer_use tool."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        status_reader: Callable[[StatusRequest], dict[str, Any]] | None = None,
        snapshot_reader: Callable[[str], str | None] | None = None,
    ) -> None:
        self.registry = registry
        self.status_reader = status_reader
        self.snapshot_reader = snapshot_reader

    def inspect(self, request: InspectRequest) -> dict[str, object]:
        if not request.device_id.strip():
            raise ValueError("device_id is required")
        return self.registry.catalog(
            CapabilityQuery(goal=request.goal)
        ).compact()

    def prepare_act(self, request: ActRequest) -> dict[str, object]:
        if not request.device_id.strip():
            raise ValueError("device_id is required")
        offer = self.registry.resolve(request.offer_id)
        if offer.provider is not CapabilityProvider.COMPUTER_USE:
            raise ValueError(
                f"offer {request.offer_id!r} belongs to an external front door; "
                "the LLM must call it directly"
            )
        required_snapshots = tuple(
            item.split(":", 1)[1]
            for item in offer.preconditions
            if item.startswith("snapshot:")
        )
        if required_snapshots:
            if self.snapshot_reader is None:
                raise RuntimeError("no trusted snapshot reader is configured")
            current_snapshot = self.snapshot_reader(request.device_id)
            if (
                request.snapshot_id not in required_snapshots
                or current_snapshot != request.snapshot_id
            ):
                raise ValueError("the current snapshot does not satisfy offer preconditions")
        return {
            "device_id": request.device_id,
            "offer_id": offer.offer_id,
            "primitive": offer.primitive.value,
            "arguments": dict(request.arguments),
            "verify": dict(request.verify),
            "snapshot_id": request.snapshot_id,
            "selection_authority": "llm",
            "executed": False,
        }

    def status(self, request: StatusRequest) -> dict[str, Any]:
        if not request.device_id.strip() or not request.operation_id.strip():
            raise ValueError("device_id and operation_id are required")
        if self.status_reader is None:
            raise RuntimeError("no status reader is configured")
        return self.status_reader(request)

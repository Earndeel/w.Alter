"""Adaptive capability offers: runtime evidence for LLM strategy selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from adaptive_operator.interruption import ActionEffects, InterruptionLevel


class Primitive(StrEnum):
    OBSERVE = "observe"
    LAUNCH_APP = "launch_app"
    FOCUS = "focus"
    OPEN_URL = "open_url"
    INVOKE = "invoke"
    TYPE = "type"
    SHORTCUT = "shortcut"
    SCROLL = "scroll"
    DRAG = "drag"
    FILESYSTEM = "filesystem"
    SYSTEM_ACTION = "system_action"
    CAPTURE = "capture"
    VISUAL_LOCATE = "visual_locate"
    VISUAL_CLICK = "visual_click"
    VERIFY = "verify"
    RESEARCH = "research"

    @classmethod
    def computer_use_runtime_primitives(cls) -> frozenset[Primitive]:
        return frozenset(item for item in cls if item is not cls.RESEARCH)


class CapabilityProvider(StrEnum):
    COMPUTER_USE = "computer_use"
    WALTER_BROWSE = "walter_browse"
    DEVICE_NODE = "device_node"


@dataclass(frozen=True)
class CostWeights:
    latency: float = 1.0
    token: float = 1.0
    interaction: float = 1.0
    disruption: float = 2.0
    failure_risk: float = 3.0


DEFAULT_COST_WEIGHTS = CostWeights()


@dataclass(frozen=True)
class CostEstimate:
    latency_ms: float
    token_cost: float
    interaction_cost: float
    disruption: float
    failure_risk: float

    def score(self, weights: CostWeights = DEFAULT_COST_WEIGHTS) -> float:
        return (
            self.latency_ms / 1000.0 * weights.latency
            + self.token_cost * weights.token
            + self.interaction_cost * weights.interaction
            + self.disruption * weights.disruption
            + self.failure_risk * weights.failure_risk
        )

    @property
    def total(self) -> float:
        """Compatibility view using the configured default weight profile."""
        return self.score()


@dataclass(frozen=True)
class CapabilityOffer:
    offer_id: str
    primitive: Primitive
    provider: CapabilityProvider
    confidence: float
    cost: CostEstimate
    effects: ActionEffects
    preconditions: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")

    @property
    def interruption_level(self) -> InterruptionLevel:
        return self.effects.level()

    @property
    def dispatch_boundary(self) -> str:
        return (
            "computer_use_runtime"
            if self.provider is CapabilityProvider.COMPUTER_USE
            else "external_front_door"
        )

    def compact(self, weights: CostWeights = DEFAULT_COST_WEIGHTS) -> dict[str, object]:
        return {
            "id": self.offer_id,
            "primitive": self.primitive.value,
            "provider": self.provider.value,
            "confidence": round(self.confidence, 3),
            "cost": round(self.cost.score(weights), 3),
            "interruption": self.interruption_level.value,
            "preconditions": list(self.preconditions),
            "boundary": self.dispatch_boundary,
        }


@dataclass(frozen=True)
class CapabilityQuery:
    goal: str | None = None
    primitives: tuple[Primitive, ...] = ()
    minimum_confidence: float = 0.0
    maximum_interruption: InterruptionLevel | None = None


@dataclass(frozen=True)
class CapabilityCatalog:
    status: str
    offers: tuple[CapabilityOffer, ...]
    weights: CostWeights = DEFAULT_COST_WEIGHTS
    executed: bool = False
    selection_authority: str = "llm"

    def compact(self) -> dict[str, object]:
        return {
            "status": self.status,
            "selection_authority": self.selection_authority,
            "executed": self.executed,
            "offers": [offer.compact(self.weights) for offer in self.offers],
        }


class CapabilityRegistry:
    def __init__(
        self,
        offers: list[CapabilityOffer],
        *,
        cost_weights: CostWeights = DEFAULT_COST_WEIGHTS,
    ) -> None:
        if len({item.offer_id for item in offers}) != len(offers):
            raise ValueError("offer ids must be unique")
        self._offers = tuple(offers)
        self.cost_weights = cost_weights

    def resolve(self, offer_id: str) -> CapabilityOffer:
        for offer in self._offers:
            if offer.offer_id == offer_id:
                return offer
        raise LookupError(f"unknown capability offer {offer_id!r}")

    def catalog(self, query: CapabilityQuery) -> CapabilityCatalog:
        selected = []
        allowed_primitives = set(query.primitives)
        levels = {
            InterruptionLevel.L0_SILENT: 0,
            InterruptionLevel.L1_WARN: 1,
            InterruptionLevel.L2_CONFIRM: 2,
        }
        for offer in self._offers:
            if allowed_primitives and offer.primitive not in allowed_primitives:
                continue
            if offer.confidence < query.minimum_confidence:
                continue
            if query.maximum_interruption is not None and (
                levels[offer.interruption_level] > levels[query.maximum_interruption]
            ):
                continue
            selected.append(offer)
        selected.sort(
            key=lambda item: (
                item.cost.score(self.cost_weights),
                -item.confidence,
                item.offer_id,
            )
        )
        return CapabilityCatalog(
            status="needs_reasoning" if selected else "no_sufficient_capability",
            offers=tuple(selected),
            weights=self.cost_weights,
        )

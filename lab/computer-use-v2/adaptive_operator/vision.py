"""Provider-neutral fast visual locator interface; perception never clicks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from adaptive_operator.observation import Rect


class LocateStatus(StrEnum):
    LOCATED = "located"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"


@dataclass(frozen=True)
class VisionBudget:
    max_latency_ms: int
    max_image_pixels: int
    max_output_tokens: int


@dataclass(frozen=True)
class GeometryHint:
    ref: str
    bounds: Rect


@dataclass(frozen=True)
class VisionPoint:
    x: int
    y: int


@dataclass(frozen=True)
class VisionLocateRequest:
    request_id: str
    snapshot_id: str
    target: str
    crop: Rect
    budget: VisionBudget
    geometry_hints: tuple[GeometryHint, ...] = ()
    diff_base_snapshot: str | None = None
    model_id: str | None = None
    click: bool = False

    def __post_init__(self) -> None:
        if self.click:
            raise ValueError("vision locator cannot dispatch clicks")
        if self.crop.width <= 0 or self.crop.height <= 0:
            raise ValueError("vision crop must be positive")
        if self.crop.width * self.crop.height > self.budget.max_image_pixels:
            raise ValueError("vision crop exceeds pixel budget")


@dataclass(frozen=True)
class VisionLocateResult:
    request_id: str
    snapshot_id: str
    status: LocateStatus
    confidence: float
    latency_ms: float
    point: VisionPoint | None = None
    ref: str | None = None
    evidence: tuple[str, ...] = ()


class FastVisualLocator:
    """Interface implemented by a benchmarked locator provider in a later lot."""

    def locate(self, request: VisionLocateRequest) -> VisionLocateResult:
        raise NotImplementedError


def validate_locate_result(
    request: VisionLocateRequest,
    result: VisionLocateResult,
    *,
    minimum_confidence: float,
) -> VisionLocateResult:
    if result.request_id != request.request_id:
        raise ValueError("visual result request id mismatch")
    if result.snapshot_id != request.snapshot_id:
        raise ValueError("visual result snapshot is stale")
    if result.status is not LocateStatus.LOCATED:
        raise ValueError(f"visual target is not located: {result.status.value}")
    if result.confidence < minimum_confidence:
        raise ValueError("visual confidence is below threshold")
    if result.point is None and result.ref is None:
        raise ValueError("located result has neither point nor ref")
    if result.point is not None:
        within = (
            request.crop.x <= result.point.x < request.crop.x + request.crop.width
            and request.crop.y <= result.point.y < request.crop.y + request.crop.height
        )
        if not within:
            raise ValueError("visual point is outside the requested crop")
    if result.latency_ms > request.budget.max_latency_ms:
        raise ValueError("visual result exceeded latency budget")
    return result

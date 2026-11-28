"""Compact, progressively disclosed observation contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ObservationDetail(StrEnum):
    MINIMAL = "minimal"
    RELEVANT = "relevant"
    DETAILED = "detailed"
    PIXELS = "pixels"


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    def to_list(self) -> list[int]:
        return [self.x, self.y, self.width, self.height]


@dataclass(frozen=True)
class RawElement:
    native_id: str
    role: str
    label: str
    bounds: Rect
    actionable: bool
    attributes: dict[str, Any] = field(default_factory=dict)
    ref_integrity: str = "native"


@dataclass(frozen=True)
class ElementRef:
    ref: str
    role: str
    label: str
    bounds: Rect | None = None
    actionable: bool = False
    attributes: dict[str, Any] = field(default_factory=dict)
    ref_integrity: str = "native"

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "ref": self.ref,
            "role": self.role,
            "label": self.label,
            "actionable": self.actionable,
            "ref_integrity": self.ref_integrity,
        }
        if self.bounds is not None:
            value["bounds"] = self.bounds.to_list()
        if self.attributes:
            value["attributes"] = self.attributes
        return value


@dataclass(frozen=True)
class ObservationRequest:
    detail: ObservationDetail = ObservationDetail.MINIMAL
    query: str | None = None
    refs: tuple[str, ...] = ()
    crop: Rect | None = None


@dataclass(frozen=True)
class CompactObservation:
    schema_version: str
    device: str
    app: str | None
    window: str | None
    focused: bool | None
    snapshot_id: str
    generation: int
    element_count: int
    elements: tuple[ElementRef, ...] = ()
    truncated: bool = False
    next_detail: ObservationDetail | None = None
    image: dict[str, Any] | None = None
    ax_chars: int = 0

    def to_dict(self) -> dict[str, Any]:
        raw: dict[str, Any] = {
            "schema_version": self.schema_version,
            "device": self.device,
            "app": self.app,
            "window": self.window,
            "focus": self.focused,
            "snapshot": self.snapshot_id,
            "generation": self.generation,
            "element_count": self.element_count,
            "truncated": self.truncated,
        }
        if self.elements:
            raw["elements"] = [item.to_dict() for item in self.elements]
        if self.next_detail is not None:
            raw["next_detail"] = self.next_detail.value
        if self.image is not None:
            raw["image"] = self.image
        return raw


class ObservationBuilder:
    def __init__(self, *, max_elements: int = 20) -> None:
        if not 1 <= max_elements <= 200:
            raise ValueError("max_elements must be between 1 and 200")
        self.max_elements = max_elements

    def build(
        self,
        *,
        device_id: str,
        app: str | None,
        window: str | None,
        focused: bool | None,
        snapshot_id: str,
        generation: int,
        elements: list[RawElement],
        request: ObservationRequest,
    ) -> CompactObservation:
        if request.detail is ObservationDetail.MINIMAL:
            return CompactObservation(
                schema_version="2.0",
                device=device_id,
                app=app,
                window=window,
                focused=focused,
                snapshot_id=snapshot_id,
                generation=generation,
                element_count=len(elements),
                next_detail=(ObservationDetail.RELEVANT if elements else None),
            )
        if request.detail is ObservationDetail.PIXELS:
            if request.crop is None:
                raise ValueError("pixels disclosure requires an explicit crop")
            return CompactObservation(
                schema_version="2.0",
                device=device_id,
                app=app,
                window=window,
                focused=focused,
                snapshot_id=snapshot_id,
                generation=generation,
                element_count=len(elements),
                image={
                    "kind": "crop",
                    "bounds": request.crop.to_list(),
                    "snapshot": snapshot_id,
                },
            )
        refs = [self._ref(item, generation, detailed=request.detail is ObservationDetail.DETAILED) for item in elements]
        if request.query:
            query = request.query.casefold()
            refs = [item for item in refs if query in f"{item.role} {item.label}".casefold()]
        if request.refs:
            wanted = set(request.refs)
            refs = [item for item in refs if item.ref in wanted]
            if request.detail is ObservationDetail.DETAILED and len(refs) != len(wanted):
                raise ValueError("a requested ref is not from the current snapshot generation")
        total_selected = len(refs)
        refs = refs[: self.max_elements]
        encoded = json.dumps([item.to_dict() for item in refs], separators=(",", ":"), ensure_ascii=False)
        next_detail = None
        if request.detail is ObservationDetail.RELEVANT and refs:
            next_detail = ObservationDetail.DETAILED
        return CompactObservation(
            schema_version="2.0",
            device=device_id,
            app=app,
            window=window,
            focused=focused,
            snapshot_id=snapshot_id,
            generation=generation,
            element_count=len(elements),
            elements=tuple(refs),
            truncated=total_selected > len(refs),
            next_detail=next_detail,
            image=None,
            ax_chars=len(encoded),
        )

    @staticmethod
    def _ref(item: RawElement, generation: int, *, detailed: bool) -> ElementRef:
        digest = hashlib.sha256(item.native_id.encode("utf-8")).hexdigest()[:8]
        return ElementRef(
            ref=f"e{generation}-{digest}",
            role=item.role,
            label=item.label[:256],
            bounds=item.bounds,
            actionable=(item.actionable and item.ref_integrity == "native"),
            attributes=dict(item.attributes) if detailed else {},
            ref_integrity=item.ref_integrity,
        )

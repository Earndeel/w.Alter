"""Adapt already-persisted V1 captures into V2 shadow observations."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from typing import Any

from adaptive_operator.observation import (
    CompactObservation,
    ObservationBuilder,
    ObservationDetail,
    ObservationRequest,
    RawElement,
    Rect,
)
from adaptive_operator.shadow_replay import ShadowReplayEvent


@dataclass(frozen=True)
class ShadowCompactionMetrics:
    raw_ax_chars: int
    compact_ax_chars: int
    raw_estimated_tokens: int
    compact_estimated_tokens: int
    reduction_percent: float
    compaction_latency_ms: float
    source_truncated_elements: int
    information_loss_elements: int
    ref_native: int
    ref_shadow_synthetic: int
    additional_backend_calls: int = 0


@dataclass(frozen=True)
class ConvertedObservation:
    observation: CompactObservation
    metrics: ShadowCompactionMetrics


class V1ObservationAdapter:
    """Convert a V1 capture result without calling its backend again."""

    def __init__(self, *, device_id: str, max_elements: int = 20) -> None:
        self.device_id = device_id
        self.builder = ObservationBuilder(max_elements=max_elements)

    def convert(
        self,
        event: ShadowReplayEvent,
        *,
        detail: ObservationDetail,
    ) -> ConvertedObservation:
        if event.action != "capture" or not isinstance(event.result, dict):
            raise ValueError("only persisted V1 capture results can be converted")
        started = time.perf_counter_ns()
        rows = event.result.get("elements")
        if not isinstance(rows, list):
            rows = []
        elements = [self._element(row, index) for index, row in enumerate(rows)]
        observation = self.builder.build(
            device_id=self.device_id,
            app=_optional_text(event.result.get("app")),
            window=_optional_text(event.result.get("window_title")),
            focused=_optional_bool(event.result.get("focused")),
            snapshot_id=f"{event.session_id}:{event.result_message_id}",
            generation=event.result_message_id,
            elements=elements,
            request=ObservationRequest(detail=detail),
        )
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        raw_chars = len(
            json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        )
        compact_chars = len(
            json.dumps(
                [item.to_dict() for item in observation.elements],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        total = _nonnegative_int(event.result.get("total_elements"), len(rows))
        source_truncated = _nonnegative_int(
            event.result.get("truncated_elements"), max(total - len(rows), 0)
        )
        native = sum(item.ref_integrity == "native" for item in elements)
        synthetic = len(elements) - native
        reduction = 0.0 if raw_chars == 0 else (raw_chars - compact_chars) / raw_chars * 100
        return ConvertedObservation(
            observation=observation,
            metrics=ShadowCompactionMetrics(
                raw_ax_chars=raw_chars,
                compact_ax_chars=compact_chars,
                raw_estimated_tokens=math.ceil(raw_chars / 4),
                compact_estimated_tokens=math.ceil(compact_chars / 4),
                reduction_percent=round(reduction, 3),
                compaction_latency_ms=round(elapsed_ms, 6),
                source_truncated_elements=source_truncated,
                information_loss_elements=max(total - len(observation.elements), 0),
                ref_native=native,
                ref_shadow_synthetic=synthetic,
                additional_backend_calls=0,
            ),
        )

    @staticmethod
    def _element(row: Any, index: int) -> RawElement:
        if not isinstance(row, dict):
            row = {}
        token = _optional_text(row.get("element_token"))
        integrity = "native" if token else "shadow_synthetic"
        native_id = token or f"v1-index:{row.get('index', index + 1)}"
        bounds = row.get("bounds")
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
            bounds = (0, 0, 0, 0)
        attributes = {
            key: value
            for key, value in row.items()
            if key not in {"index", "element_token", "role", "label", "bounds"}
        }
        return RawElement(
            native_id=native_id,
            role=str(row.get("role") or "unknown"),
            label=str(row.get("label") or ""),
            bounds=Rect(*(_nonnegative_int(value, 0) for value in bounds)),
            actionable=bool(row.get("enabled", True)),
            attributes=attributes,
            ref_integrity=integrity,
        )


def _optional_text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _nonnegative_int(value: Any, default: int) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default
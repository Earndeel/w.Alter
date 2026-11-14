"""Out-of-process, fail-isolated observer for persisted V1 Computer Use events."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from adaptive_operator.device_context import DeviceActivity
from adaptive_operator.observation import ObservationDetail
from adaptive_operator.shadow_observation import V1ObservationAdapter
from adaptive_operator.shadow_policy import ShadowInterruptionClassifier
from adaptive_operator.shadow_replay import ShadowReplayReader


@dataclass(frozen=True)
class ShadowTelemetryRecord:
    call_id: str
    result_message_id: int
    action: str | None
    v1_persisted_interval_ms: float
    observation: dict[str, Any] | None
    compaction: dict[str, Any] | None
    policy: dict[str, Any]
    shadow_error: str | None = None
    schema_version: str = "2.1"


@dataclass(frozen=True)
class ShadowPollResult:
    records: tuple[ShadowTelemetryRecord, ...]
    next_cursor: int
    additional_backend_calls: int
    failures_affecting_v1: int = 0
    replay_errors: tuple[str, ...] = ()


class ShadowSidecar:
    """Replay completed V1 results; never import or call a Computer Use backend."""

    def __init__(
        self,
        *,
        database: str | Path,
        device_id: str,
        detail: ObservationDetail = ObservationDetail.RELEVANT,
        max_elements: int = 20,
        activity: DeviceActivity | None = None,
        batch_size: int = 100,
    ) -> None:
        self.reader = ShadowReplayReader(database, batch_size=batch_size)
        self.adapter = V1ObservationAdapter(
            device_id=device_id, max_elements=max_elements
        )
        self.classifier = ShadowInterruptionClassifier()
        self.detail = detail
        self.activity = activity

    def poll_once(self, *, cursor: int) -> ShadowPollResult:
        batch = self.reader.read_after(cursor)
        records: list[ShadowTelemetryRecord] = []
        for event in batch.events:
            observation = None
            compaction = None
            shadow_error = None
            if event.action == "capture":
                try:
                    converted = self.adapter.convert(event, detail=self.detail)
                    observation = converted.observation.to_dict()
                    compaction = asdict(converted.metrics)
                except Exception as exc:  # event-scoped isolation is deliberate
                    shadow_error = f"{type(exc).__name__}:{exc}"
            prediction = self.classifier.classify(
                event, activity=self.activity
            )
            policy = {
                "classification_status": prediction.classification_status,
                "predicted_level": (
                    prediction.predicted_level.value
                    if prediction.predicted_level is not None
                    else None
                ),
                "would_warn": prediction.would_warn,
                "would_confirm": prediction.would_confirm,
                "user_active": prediction.user_active,
                "reason": prediction.reason,
                "enforced": prediction.enforced,
                "blocked_v1": prediction.blocked_v1,
                "observed_effects": asdict(prediction.observed_effects),
            }
            records.append(
                ShadowTelemetryRecord(
                    call_id=event.call_id,
                    result_message_id=event.result_message_id,
                    action=event.action,
                    v1_persisted_interval_ms=max(
                        (event.completed_at - event.called_at) * 1000.0, 0.0
                    ),
                    observation=observation,
                    compaction=compaction,
                    policy=policy,
                    shadow_error=shadow_error,
                )
            )
        return ShadowPollResult(
            records=tuple(records),
            next_cursor=batch.next_cursor,
            additional_backend_calls=batch.additional_backend_calls,
            failures_affecting_v1=0,
            replay_errors=batch.errors,
        )

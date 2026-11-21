"""Evidence-first benchmark contracts for Computer Use V2."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class RunMode(StrEnum):
    CONTRACT = "contract"
    LIVE_MACOS = "live_macos"


class MetricKind(StrEnum):
    LLM_CALL = "llm_call"
    COMPUTER_USE_CALL = "computer_use_call"
    WALTER_BROWSE_CALL = "walter_browse_call"
    SCREENSHOT = "screenshot"
    VISION_CALL = "vision_call"
    AX_PAYLOAD = "ax_payload"
    FOCUS_CHANGE = "focus_change"
    MOUSE_MOVEMENT = "mouse_movement"
    INTERRUPTION_WARNING = "interruption_warning"
    RETRY = "retry"
    POSTCONDITION = "postcondition"
    ROUTE = "route"


@dataclass(frozen=True)
class BenchmarkScenario:
    scenario_id: str
    title: str
    goal: str
    expected_route: tuple[str, ...]
    postcondition: dict[str, Any]
    expected_walter_browse_min: int = 0
    expected_walter_browse_max: int | None = None
    expected_screenshots_min: int = 0
    expected_screenshots_max: int | None = None
    expected_vision_calls_min: int = 0
    expected_vision_calls_max: int | None = None
    expected_interruption_warnings_min: int = 0
    user_active: bool = False
    max_interruption: str = "L1"


@dataclass(frozen=True)
class MetricEvent:
    at: float
    kind: MetricKind
    data: dict[str, Any] = field(default_factory=dict)

    def append_jsonl(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"at": self.at, "kind": self.kind.value, "data": self.data},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )


@dataclass(frozen=True)
class BenchmarkRun:
    run_id: str
    scenario_id: str
    mode: RunMode
    started_at: float
    ended_at: float
    events: tuple[MetricEvent, ...]


@dataclass(frozen=True)
class BenchmarkMetrics:
    success: bool
    total_latency_ms: float
    llm_calls: int
    computer_use_calls: int
    walter_browse_calls: int
    screenshots: int
    vision_calls: int
    ax_chars: int
    ax_tokens: int
    input_tokens: int
    output_tokens: int
    focus_changes: int
    mouse_movements: int
    interruption_warnings: int
    retries: int
    evidence_class: str


def load_scenarios(path: str | Path) -> tuple[BenchmarkScenario, ...]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("scenario manifest must be a JSON array")
    result = []
    for row in rows:
        item = dict(row)
        item["expected_route"] = tuple(item["expected_route"])
        result.append(BenchmarkScenario(**item))
    if len({item.scenario_id for item in result}) != len(result):
        raise ValueError("scenario ids must be unique")
    return tuple(result)


def aggregate_run(run: BenchmarkRun) -> BenchmarkMetrics:
    if run.ended_at < run.started_at:
        raise ValueError("benchmark ended before it started")

    def count(kind: MetricKind) -> int:
        return sum(item.kind is kind for item in run.events)

    llm = [item for item in run.events if item.kind is MetricKind.LLM_CALL]
    ax = [item for item in run.events if item.kind is MetricKind.AX_PAYLOAD]
    postconditions = [item for item in run.events if item.kind is MetricKind.POSTCONDITION]
    return BenchmarkMetrics(
        success=bool(postconditions) and postconditions[-1].data.get("satisfied") is True,
        total_latency_ms=round((run.ended_at - run.started_at) * 1000, 3),
        llm_calls=len(llm),
        computer_use_calls=count(MetricKind.COMPUTER_USE_CALL),
        walter_browse_calls=count(MetricKind.WALTER_BROWSE_CALL),
        screenshots=count(MetricKind.SCREENSHOT),
        vision_calls=count(MetricKind.VISION_CALL),
        ax_chars=sum(int(item.data.get("chars", 0)) for item in ax),
        ax_tokens=sum(int(item.data.get("tokens", 0)) for item in ax),
        input_tokens=sum(int(item.data.get("input_tokens", 0)) for item in llm),
        output_tokens=sum(int(item.data.get("output_tokens", 0)) for item in llm),
        focus_changes=count(MetricKind.FOCUS_CHANGE),
        mouse_movements=count(MetricKind.MOUSE_MOVEMENT),
        interruption_warnings=count(MetricKind.INTERRUPTION_WARNING),
        retries=count(MetricKind.RETRY),
        evidence_class=("live_macos" if run.mode is RunMode.LIVE_MACOS else "contract_only"),
    )


def validate_run(scenario: BenchmarkScenario, run: BenchmarkRun) -> BenchmarkMetrics:
    if run.scenario_id != scenario.scenario_id:
        raise ValueError("run scenario id mismatch")
    metrics = aggregate_run(run)
    if metrics.walter_browse_calls < scenario.expected_walter_browse_min:
        raise ValueError("required walter_browse call is missing")
    if (
        scenario.expected_walter_browse_max is not None
        and metrics.walter_browse_calls > scenario.expected_walter_browse_max
    ):
        raise ValueError("walter_browse call budget exceeded")
    if metrics.screenshots < scenario.expected_screenshots_min:
        raise ValueError("required screenshot evidence is missing")
    if (
        scenario.expected_screenshots_max is not None
        and metrics.screenshots > scenario.expected_screenshots_max
    ):
        raise ValueError("screenshot budget exceeded")
    if metrics.vision_calls < scenario.expected_vision_calls_min:
        raise ValueError("required vision evidence is missing")
    if (
        scenario.expected_vision_calls_max is not None
        and metrics.vision_calls > scenario.expected_vision_calls_max
    ):
        raise ValueError("vision call budget exceeded")
    if metrics.interruption_warnings < scenario.expected_interruption_warnings_min:
        raise ValueError("required interruption warning is missing")
    if scenario.user_active and metrics.focus_changes > 0 and metrics.interruption_warnings == 0:
        raise ValueError("active-user focus change occurred without interruption warning")
    route = [item.data.get("name") for item in run.events if item.kind is MetricKind.ROUTE]
    expected = list(scenario.expected_route)
    if expected and not route:
        raise ValueError("required route evidence is missing")
    if route and not _is_subsequence(expected, route):
        raise ValueError("observed route does not preserve expected route ordering")
    return metrics


def _is_subsequence(expected: list[str], observed: list[Any]) -> bool:
    iterator = iter(observed)
    return all(any(candidate == wanted for candidate in iterator) for wanted in expected)

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adaptive_operator.benchmark import (
    BenchmarkRun,
    BenchmarkScenario,
    MetricEvent,
    MetricKind,
    RunMode,
    aggregate_run,
    load_scenarios,
    validate_run,
)


REQUIRED = {
    "A_launch_safari",
    "B_launch_finder",
    "C_finder_downloads",
    "D_ax_click",
    "E_visual_click",
    "F_unknown_app_observe",
    "G_web_docs_then_computer_use",
    "H_active_user_same_task",
}


def test_scenario_manifest_contains_all_required_cases_and_safety_contracts():
    scenarios = load_scenarios(Path("benchmarks/scenarios.json"))

    assert {item.scenario_id for item in scenarios} == REQUIRED
    assert all(item.expected_route for item in scenarios)
    assert all(item.postcondition for item in scenarios)
    assert next(x for x in scenarios if x.scenario_id.startswith("G_")).expected_walter_browse_min == 1
    visual = next(x for x in scenarios if x.scenario_id.startswith("E_"))
    assert visual.expected_screenshots_min == visual.expected_screenshots_max == 1
    assert visual.expected_vision_calls_min == visual.expected_vision_calls_max == 1
    assert next(x for x in scenarios if x.scenario_id.startswith("H_")).user_active is True


def test_aggregate_computes_every_requested_metric_from_events():
    run = BenchmarkRun(
        run_id="run-1",
        scenario_id="E_visual_click",
        mode=RunMode.CONTRACT,
        started_at=10.0,
        ended_at=11.2,
        events=(
            MetricEvent(10.1, MetricKind.LLM_CALL, {"input_tokens": 100, "output_tokens": 20}),
            MetricEvent(10.2, MetricKind.COMPUTER_USE_CALL, {}),
            MetricEvent(10.3, MetricKind.SCREENSHOT, {}),
            MetricEvent(10.4, MetricKind.VISION_CALL, {}),
            MetricEvent(10.5, MetricKind.AX_PAYLOAD, {"chars": 40, "tokens": 10}),
            MetricEvent(10.6, MetricKind.MOUSE_MOVEMENT, {}),
            MetricEvent(10.7, MetricKind.FOCUS_CHANGE, {}),
            MetricEvent(10.8, MetricKind.INTERRUPTION_WARNING, {}),
            MetricEvent(10.9, MetricKind.RETRY, {}),
            MetricEvent(11.0, MetricKind.POSTCONDITION, {"satisfied": True}),
        ),
    )

    metrics = aggregate_run(run)

    assert metrics.success is True
    assert metrics.total_latency_ms == pytest.approx(1200)
    assert metrics.llm_calls == 1
    assert metrics.computer_use_calls == 1
    assert metrics.walter_browse_calls == 0
    assert metrics.screenshots == 1
    assert metrics.vision_calls == 1
    assert metrics.ax_chars == 40
    assert metrics.ax_tokens == 10
    assert metrics.input_tokens == 100
    assert metrics.output_tokens == 20
    assert metrics.focus_changes == 1
    assert metrics.mouse_movements == 1
    assert metrics.interruption_warnings == 1
    assert metrics.retries == 1


def test_contract_run_cannot_claim_live_success_and_sequence_is_validated():
    scenario = BenchmarkScenario(
        scenario_id="G_web_docs_then_computer_use",
        title="docs then device",
        goal="test",
        expected_route=("walter_browse", "computer_use"),
        postcondition={"done": True},
        expected_walter_browse_min=1,
    )
    run = BenchmarkRun(
        run_id="run-1",
        scenario_id=scenario.scenario_id,
        mode=RunMode.CONTRACT,
        started_at=1.0,
        ended_at=2.0,
        events=(MetricEvent(1.5, MetricKind.POSTCONDITION, {"satisfied": True}),),
    )

    with pytest.raises(ValueError, match="walter_browse"):
        validate_run(scenario, run)

    assert aggregate_run(run).evidence_class == "contract_only"


def test_validation_rejects_missing_route_evidence():
    scenario = BenchmarkScenario(
        scenario_id="A",
        title="launch",
        goal="test",
        expected_route=("computer_use", "native.launch_app", "verify"),
        postcondition={"done": True},
    )
    run = BenchmarkRun(
        run_id="missing-route",
        scenario_id="A",
        mode=RunMode.CONTRACT,
        started_at=0.0,
        ended_at=1.0,
        events=(MetricEvent(1.0, MetricKind.POSTCONDITION, {"satisfied": True}),),
    )

    with pytest.raises(ValueError, match="route evidence"):
        validate_run(scenario, run)


def test_jsonl_roundtrip_is_append_only_event_evidence(tmp_path):
    event = MetricEvent(1.0, MetricKind.COMPUTER_USE_CALL, {"action": "goal"})
    path = tmp_path / "trace.jsonl"
    event.append_jsonl(path)
    event.append_jsonl(path)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["kind"] == "computer_use_call"

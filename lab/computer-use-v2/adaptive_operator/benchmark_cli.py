"""CLI for validating the V2 benchmark instrumentation contract.

It intentionally implements only contract-mode synthetic traces. Live macOS
execution is added only after the adapter and safety gate are integrated.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from adaptive_operator.benchmark import (
    BenchmarkRun,
    BenchmarkScenario,
    MetricEvent,
    MetricKind,
    RunMode,
    load_scenarios,
    validate_run,
)


def _scenario_from_mapping(raw: dict[str, Any]) -> BenchmarkScenario:
    value = dict(raw)
    value["expected_route"] = tuple(value["expected_route"])
    return BenchmarkScenario(**value)


def simulate_contract_run(
    scenario: BenchmarkScenario | dict[str, Any], *, output_dir: str | Path
) -> dict[str, Any]:
    """Exercise the event/validation pipeline without claiming device execution."""
    if isinstance(scenario, dict):
        scenario = _scenario_from_mapping(scenario)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    events: list[MetricEvent] = [
        MetricEvent(0.001, MetricKind.LLM_CALL, {"input_tokens": 100, "output_tokens": 20}),
        MetricEvent(0.002, MetricKind.COMPUTER_USE_CALL),
    ]
    if scenario.expected_walter_browse_min:
        events.extend(
            MetricEvent(0.003 + index / 1000, MetricKind.WALTER_BROWSE_CALL)
            for index in range(scenario.expected_walter_browse_min)
        )
    events.extend(
        MetricEvent(0.006 + index / 1000, MetricKind.SCREENSHOT)
        for index in range(scenario.expected_screenshots_min)
    )
    events.extend(
        MetricEvent(0.008 + index / 1000, MetricKind.VISION_CALL)
        for index in range(scenario.expected_vision_calls_min)
    )
    for index, name in enumerate(scenario.expected_route, start=4):
        events.append(MetricEvent(index / 1000, MetricKind.ROUTE, {"name": name}))
    if scenario.expected_interruption_warnings_min:
        events.extend(
            MetricEvent(0.020 + index / 1000, MetricKind.INTERRUPTION_WARNING)
            for index in range(scenario.expected_interruption_warnings_min)
        )
    events.append(MetricEvent(0.030, MetricKind.POSTCONDITION, {"satisfied": True}))
    run = BenchmarkRun(
        run_id=f"contract-{scenario.scenario_id}",
        scenario_id=scenario.scenario_id,
        mode=RunMode.CONTRACT,
        started_at=0.0,
        ended_at=0.031,
        events=tuple(events),
    )
    trace_path = target / f"{scenario.scenario_id}.events.jsonl"
    for event in events:
        event.append_jsonl(trace_path)
    metrics = validate_run(scenario, run)
    report = {
        "scenario_id": scenario.scenario_id,
        "mode": RunMode.CONTRACT.value,
        "live_execution_performed": False,
        "trace_path": str(trace_path),
        "metrics": asdict(metrics),
    }
    report_path = target / f"{scenario.scenario_id}.report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="computer-use-v2-benchmark")
    subparsers = parser.add_subparsers(dest="command", required=True)
    contract = subparsers.add_parser("contract")
    contract.add_argument("--scenarios", required=True)
    contract.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command != "contract":
        raise AssertionError("unreachable")
    scenarios = load_scenarios(args.scenarios)
    reports = [simulate_contract_run(item, output_dir=args.output) for item in scenarios]
    payload = {
        "mode": RunMode.CONTRACT.value,
        "live_execution_performed": False,
        "scenario_count": len(reports),
        "success_count": sum(item["metrics"]["success"] is True for item in reports),
        "output": str(Path(args.output).resolve()),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

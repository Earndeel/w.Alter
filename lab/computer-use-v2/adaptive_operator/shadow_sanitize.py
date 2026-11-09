"""Produce the shareable evidence subset of a private shadow report."""

from __future__ import annotations

from typing import Any


_TOP_LEVEL = (
    "schema_version",
    "mode",
    "passed",
    "failures",
    "evidence_class",
    "postcondition_satisfied",
    "measurement_basis",
    "v1_event_count",
    "replay_quarantine_count",
    "warmup_runs_per_measured_scenario",
    "measured_runs_per_scenario",
    "measurements",
    "measurements_global",
    "device_context_cache",
    "policy",
    "counters",
    "integrity",
    "gates",
)


def sanitize_benchmark_report(report: dict[str, Any]) -> dict[str, Any]:
    output = {key: report[key] for key in _TOP_LEVEL if key in report}
    scenarios = []
    for item in report.get("scenarios", ()):
        scenarios.append({
            key: item[key]
            for key in (
                "id",
                "name",
                "status",
                "reason",
                "element_count",
                "external_provider",
                "computer_use_executes_provider",
            )
            if key in item
        })
    output["scenarios"] = scenarios
    return output

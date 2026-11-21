from __future__ import annotations

import json
from pathlib import Path

import pytest

from adaptive_operator.benchmark import RunMode
from adaptive_operator.benchmark_cli import main, simulate_contract_run


def test_simulated_contract_run_covers_route_and_postcondition(tmp_path: Path) -> None:
    scenarios = json.loads(Path("benchmarks/scenarios.json").read_text(encoding="utf-8"))
    scenario = next(item for item in scenarios if item["scenario_id"] == "G_web_docs_then_computer_use")
    report = simulate_contract_run(scenario, output_dir=tmp_path)
    assert report["metrics"]["success"] is True
    assert report["metrics"]["walter_browse_calls"] == 1
    assert report["metrics"]["evidence_class"] == "contract_only"
    assert report["live_execution_performed"] is False
    assert Path(report["trace_path"]).exists()


def test_cli_contract_writes_all_eight_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main([
        "contract",
        "--scenarios", "benchmarks/scenarios.json",
        "--output", str(tmp_path),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["mode"] == RunMode.CONTRACT.value
    assert payload["live_execution_performed"] is False
    assert payload["scenario_count"] == 8
    assert payload["success_count"] == 8
    assert len(list(tmp_path.glob("*.report.json"))) == 8


def test_cli_has_no_fake_live_mode(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["live", "--output", str(tmp_path)])

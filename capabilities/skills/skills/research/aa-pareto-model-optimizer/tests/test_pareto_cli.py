from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "pareto.py"


def test_pareto_cli_uses_marginal_cost_cap_by_default(tmp_path: Path) -> None:
    rows = [
        {"name": "MiMo-V2.6-Pro", "intel": 46.3242065310383, "total_cost_usd": 0.13322318937213493},
        {"name": "GPT-6 Sol (max)", "intel": 47.5276426437724, "total_cost_usd": 1.0564240894076389},
        {"name": "Claude Opus 5.5 (medium)", "intel": 51.2434931792768, "total_cost_usd": 1.3360093438976588},
        {"name": "Claude Opus 5.5 (high)", "intel": 53.5831959822067, "total_cost_usd": 1.822504718771704},
        {"name": "Claude Opus 5.5 (xhigh)", "intel": 55.9873505840139, "total_cost_usd": 3.459110175822289},
        {"name": "Claude Opus 5.5 (max)", "intel": 57.6223698102963, "total_cost_usd": 5.982012019521066},
    ]
    input_path = tmp_path / "snapshot.json"
    input_path.write_text(json.dumps({"data": rows}), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(input_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["max_incremental_cost_per_score_point"] == 0.75
    assert [row["name"] for row in result["pragmatic_frontier"]] == [
        "MiMo-V2.6-Pro",
        "Claude Opus 5.5 (medium)",
        "Claude Opus 5.5 (high)",
        "Claude Opus 5.5 (xhigh)",
    ]
    removed = result["removed_by_cost_inefficiency"]
    assert [row["name"] for row in removed] == [
        "GPT-6 Sol (max)",
        "Claude Opus 5.5 (max)",
    ]
    assert removed[0]["previous_model"] == "MiMo-V2.6-Pro"
    assert result["upgrade_ladder"]["quality_ceiling"]["model"] == "Claude Opus 5.5 (max)"
